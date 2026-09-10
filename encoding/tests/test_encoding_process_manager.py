#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
import threading
import time
import unittest

from encoding import EncodingAlreadyInProgressError
from encoding import encoding_process_manager as epm


class InitializeEncodingDBTestCase(unittest.TestCase):
    db_filename = 'test_encoding_init.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_initialize_encoding_db_creates_table(self):
        epm.initialize_encoding_db(self.db_filename)
        self.assertTrue(os.path.exists(self.db_filename))

        with epm.SQLite(self.db_filename) as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            self.assertIn(epm.ENCODING_QUEUE_TABLE, tables)

    def test_initialize_encoding_db_is_idempotent(self):
        # Calling it twice (e.g. once per worker) must not blow up on an
        # existing table.
        epm.initialize_encoding_db(self.db_filename)
        epm.initialize_encoding_db(self.db_filename)


class SqliteEncodingQueueTestCase(unittest.TestCase):
    """Exercises the queue backend directly - the atomic-claim contract,
    and the transitions a dispatcher drives it through. It's a pure queue:
    a row means queued-or-running, and the row is deleted when the job is
    done. There is no stored status or exit code."""

    db_filename = 'test_encoding_queue.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)
        epm.initialize_encoding_db(self.db_filename)
        self.queue = epm.SqliteEncodingQueue(self.db_filename)

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_enqueue_then_find(self):
        command = ["ffmpeg", "-i", "in.mp4", "out.mp4"]
        self.queue.enqueue("video1", command)

        row = self.queue.find("video1")
        self.assertIsNotNone(row)
        self.assertEqual(row['lock_name'], "video1")
        self.assertIsNone(row['pid'])  # queued, not yet spawned

    def test_enqueue_twice_raises_already_in_progress(self):
        self.queue.enqueue("video1", ["ffmpeg"])
        with self.assertRaises(EncodingAlreadyInProgressError):
            self.queue.enqueue("video1", ["ffmpeg", "-different", "args"])

    def test_enqueue_again_after_delete_is_allowed(self):
        # The whole point of a pure queue: once a job's row is gone, the
        # same lock_name can be re-queued for a re-encode. No tombstone.
        self.queue.enqueue("video1", ["ffmpeg"])
        self.queue.mark_running("video1", pid=1)
        self.queue.delete("video1")

        self.queue.enqueue("video1", ["ffmpeg", "-again"])  # must not raise
        self.assertIsNotNone(self.queue.find("video1"))

    def test_poll_pending_only_returns_unclaimed_jobs(self):
        self.queue.enqueue("video1", ["ffmpeg"])
        self.queue.enqueue("video2", ["ffmpeg"])
        self.queue.mark_running("video1", pid=1234)

        pending = self.queue.poll_pending(limit=10)
        pending_names = [row['lock_name'] for row in pending]

        self.assertIn("video2", pending_names)
        self.assertNotIn("video1", pending_names)

    def test_poll_pending_respects_limit(self):
        for i in range(5):
            self.queue.enqueue(f"video{i}", ["ffmpeg"])

        pending = self.queue.poll_pending(limit=2)
        self.assertEqual(len(pending), 2)

    def test_poll_pending_is_fifo(self):
        for name in ("a", "b", "c"):
            self.queue.enqueue(name, ["ffmpeg"])
        order = [row['lock_name'] for row in self.queue.poll_pending(limit=10)]
        self.assertEqual(order, ["a", "b", "c"])

    def test_mark_running_sets_pid(self):
        self.queue.enqueue("video1", ["ffmpeg"])
        self.queue.mark_running("video1", pid=4321)

        row = self.queue.find("video1")
        self.assertEqual(row['pid'], 4321)

    def test_delete_removes_row(self):
        self.queue.enqueue("video1", ["ffmpeg"])
        self.queue.delete("video1")
        self.assertIsNone(self.queue.find("video1"))

    def test_delete_missing_row_is_noop(self):
        self.queue.delete("never-existed")  # must not raise


class ModuleInterfaceTestCase(unittest.TestCase):
    """Tests the 3 module-level functions EncodingManager calls
    (lock_encoding, update_lock, in_progress), against the module-level
    default queue - same shape as EncodingManager itself calls them."""

    db_filename = 'test_encoding_interface.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)
        epm.initialize_encoding_db(self.db_filename)

        # point the module-level default queue at our throwaway db instead
        # of the real DB_PATH, and restore it afterward.
        self._original_queue = epm._queue
        epm._queue = epm.SqliteEncodingQueue(self.db_filename)

    def tearDown(self):
        epm._queue = self._original_queue
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_lock_encoding_then_in_progress(self):
        self.assertFalse(epm.in_progress("video1"))

        epm.lock_encoding("video1", ["ffmpeg", "-i", "video1"])

        self.assertTrue(epm.in_progress("video1"))

    def test_lock_encoding_twice_raises(self):
        epm.lock_encoding("video1", ["ffmpeg"])
        with self.assertRaises(EncodingAlreadyInProgressError):
            epm.lock_encoding("video1", ["ffmpeg"])

    def test_update_lock_sets_pid_and_stays_in_progress(self):
        epm.lock_encoding("video1", ["ffmpeg"])
        epm.update_lock("video1", 999)

        row = epm._queue.find("video1")
        self.assertEqual(row['pid'], 999)
        self.assertTrue(epm.in_progress("video1"))

    def test_in_progress_false_once_row_deleted(self):
        epm.lock_encoding("video1", ["ffmpeg"])
        epm.update_lock("video1", 999)
        epm._queue.delete("video1")

        self.assertFalse(epm.in_progress("video1"))

    def test_in_progress_false_for_unknown_lock_name(self):
        self.assertFalse(epm.in_progress("never-queued"))


class DispatcherTestCase(unittest.TestCase):
    """Exercises the actual dispatch loop end-to-end: enqueue a real,
    trivial subprocess command, let _dispatch_once spawn and supervise
    it, and confirm the queue row is gone once the supervise thread has
    reaped it (pure queue - finished means deleted)."""

    db_filename = 'test_encoding_dispatch.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)
        epm.initialize_encoding_db(self.db_filename)
        self.queue = epm.SqliteEncodingQueue(self.db_filename)
        self.executor = epm.LocalSubprocessExecutor()

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def _dispatch_and_wait(self, pool_size=2, timeout=5):
        active = {}
        active_lock = threading.Lock()
        epm._dispatch_once(self.queue, self.executor, active, active_lock, pool_size)

        deadline = time.time() + timeout
        while active and time.time() < deadline:
            time.sleep(0.05)
        return active

    def test_dispatch_runs_job_then_deletes_row(self):
        self.queue.enqueue("video1", ["true"])  # exits 0 immediately

        active = self._dispatch_and_wait()

        self.assertEqual(active, {}, "supervise thread should have reaped the job")
        self.assertIsNone(self.queue.find("video1"), "row should be gone after completion")

    def test_dispatch_deletes_row_on_nonzero_exit(self):
        self.queue.enqueue("video1", ["false"])  # exits 1 immediately

        self._dispatch_and_wait()

        # Pure queue: failure is logged, not stored - the row just goes.
        self.assertIsNone(self.queue.find("video1"))

    def test_dispatch_sets_pid_while_running(self):
        self.queue.enqueue("video1", ["sleep", "0.5"])

        active = {}
        active_lock = threading.Lock()
        epm._dispatch_once(self.queue, self.executor, active, active_lock, pool_size=2)

        # mid-run: row still present, pid recorded
        row = self.queue.find("video1")
        self.assertIsNotNone(row)
        self.assertIsNotNone(row['pid'])

        deadline = time.time() + 5
        while active and time.time() < deadline:
            time.sleep(0.05)
        self.assertIsNone(self.queue.find("video1"))

    def test_dispatch_respects_pool_size(self):
        # 3 jobs queued, but pool_size=1 - only one should be picked up
        # in a single dispatch pass, the other two stay queued.
        self.queue.enqueue("video1", ["sleep", "0.3"])
        self.queue.enqueue("video2", ["sleep", "0.3"])
        self.queue.enqueue("video3", ["sleep", "0.3"])

        active = {}
        active_lock = threading.Lock()
        epm._dispatch_once(self.queue, self.executor, active, active_lock, pool_size=1)

        self.assertEqual(len(active), 1)
        still_queued = [row['lock_name'] for row in self.queue.poll_pending(limit=10)]
        self.assertEqual(len(still_queued), 2)

        # let it finish so the daemon thread doesn't outlive the test
        deadline = time.time() + 5
        while active and time.time() < deadline:
            time.sleep(0.05)

    def test_dispatch_drops_unspawnable_command(self):
        self.queue.enqueue("video1", ["this-binary-does-not-exist-anywhere"])

        active = self._dispatch_and_wait()

        self.assertEqual(active, {})
        self.assertIsNone(self.queue.find("video1"), "unspawnable job row should be dropped")


if __name__ == "__main__":
    unittest.main()
