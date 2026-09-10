#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
encoding_process_manager owns the ABR encoding job queue, and is the only
piece of CasterPak that actually spawns and reaps ffmpeg processes for
background ABR encoding.

Two jobs, deliberately kept in one small module:

1. The interface EncodingManager talks to, to queue and inspect jobs:
   lock_encoding(lock_name, command), update_lock(lock_name, pid),
   in_progress(lock_name).

2. The dispatcher: a background thread, started from gunicorn's
   on_starting hook (see gunicorn.conf.py - same shape as cleanup's
   start_maintenance_loop), that polls the queue table, spawns pending
   jobs up to max_concurrent_encodes at a time, and waits on each child
   itself. Because this module is the true parent of every encoding
   process, wait() here gets the real exit code (logged to encoding_log)
   - this replaces the old `signal.signal(SIGCHLD, SIG_IGN)` hack that
   used to live in encodingmanager.py, which auto-reaped children at the
   kernel level and so made exit codes unrecoverable by anyone.

This table is a PURE PROCESS QUEUE, not a log: a row means "an encode for
this lock_name is queued or running", nothing more. The row is DELETED
the moment the process returns - success or failure alike. Exit status is
logged, never stored. So there is no terminal state a row can get stuck
in: if a row exists, an encode really is in flight.

The queue backend (today: sqlite) and the execution backend (today: local
subprocess) are two small, separate interfaces on purpose -
SqliteEncodingQueue / LocalSubprocessExecutor below - so a future
Kafka-backed queue or Fargate/Lambda-backed executor can be swapped in
independently later, without the dispatch loop itself changing.
"""
import json
import logging
import random
import sqlite3
import subprocess
import threading
import time
import typing as t

from cachedb import SQLite, DB_PATH
from config import get_config

from . import EncodingAlreadyInProgressError

logger = logging.getLogger('CasterPak-encoding')

ENCODING_QUEUE_TABLE = 'encodingqueue'


# ####################################################################### #
# ######################## SECURITY TODO ############################### #
# ####################################################################### #
# The `command` column of the encodingqueue table holds a ready-to-exec
# argv list, and the dispatcher runs it VERBATIM:
#     poll_pending() -> _dispatch_once() -> executor.spawn() -> Popen(cmd)
# Anything that can INSERT a row into cacheDB.db therefore has arbitrary
# command execution inside the gunicorn master process. cacheDB.db is a
# plain file on a writable volume shared with the cache tables - this is
# not a theoretical hole.
#
# Fix direction: the queue must NOT store executable commands. Persist
# only the parameters an encode needs (source path, ladder, output dir),
# and have the dispatcher rebuild the argv from a trusted builder
# (EncodingManager.get_ffmpeg_command) at spawn time. Then a poisoned row
# can at worst request an encode of a path, not run a shell.
#
# Every call site on the command's path - here and in
# encoding/encodingmanager.py - is tagged `SECURITY TODO (see banner)` so
# `grep -rn "SECURITY TODO"` finds the whole blast radius.
# ####################################################################### #

# NOTE on row lifecycle: rows delete themselves when the process returns
# (see _supervise -> queue.delete). The one way to orphan a row is to
# hard-kill the gunicorn master while a job is running (pid set) - the
# supervising thread dies with it and never deletes. A startup reaper
# (check `pid` liveness with os.kill(pid, 0), drop the dead ones) would
# close that gap; not built yet.


def initialize_encoding_db(dbname: str = DB_PATH) -> None:
    """Create the encoding queue table if it doesn't exist. Called once at
    application startup (see casterpak/__init__.py's create_app), the same
    way cachedb.initialize_cache_db() is - and reuses the same db file and
    the same SQLite context-manager class.

    Three columns, nothing more: the lock_name claim, the command to run,
    and the pid once it's running (NULL while still queued). Insertion
    order (rowid) is the queue order.
    """
    with SQLite(dbname) as cursor:
        cursor.execute(f"""CREATE TABLE IF NOT EXISTS {ENCODING_QUEUE_TABLE} (
                           lock_name  TEXT PRIMARY KEY,
                           command    TEXT NOT NULL,
                           pid        INTEGER
                         );
                      """)
        logger.debug(f"Ensured table '{ENCODING_QUEUE_TABLE}' exists in database {dbname}")


# ---------------------------------------------------------------------------
# EncodingQueue - the queue backend. SqliteEncodingQueue today; a
# Kafka-backed queue would satisfy the same handful of methods.
#
# TODO: SqliteEncodingQueue and LocalSubprocessExecutor are hardcoded into
# this module (the `_queue` default below, and start_encoding_dispatcher's
# body). They should sit behind a config-selected factory - same shape as
# vodhls/factory.py's `input_type` switch - so swapping the backend is a
# config change, not an edit here. Possibly their own module(s) too.
# ---------------------------------------------------------------------------

class SqliteEncodingQueue:
    def __init__(self, dbname: str = DB_PATH):
        self.dbname = dbname

    def enqueue(self, lock_name: str, command: t.List[str]) -> None:
        """Atomically claim lock_name and persist the command to run for
        it. The INSERT is the lock: lock_name is the PRIMARY KEY, so a
        second enqueue() for a lock_name that's still queued or running
        hits a UNIQUE constraint, and we turn that into
        EncodingAlreadyInProgressError. Once the job finishes its row is
        gone, so the same lock_name can be enqueued again for a re-encode."""
        try:
            with SQLite(self.dbname) as cursor:
                # ###### SECURITY TODO (see banner): `command` gets persisted here
                # as an argv the dispatcher will later exec with no revalidation ######
                cursor.execute(
                    f"""INSERT INTO {ENCODING_QUEUE_TABLE} (lock_name, command)
                        VALUES (?, ?)""",
                    (lock_name, json.dumps(command)),
                )
        except sqlite3.IntegrityError:
            raise EncodingAlreadyInProgressError(
                f"an encoding job is already queued for {lock_name!r}"
            )

    def poll_pending(self, limit: int) -> t.List[sqlite3.Row]:
        """Return up to `limit` claimed-but-not-yet-spawned jobs (pid IS
        NULL), oldest first (by insertion order)."""
        with SQLite(self.dbname) as cursor:
            # ###### SECURITY TODO (see banner): the `command` in each row returned
            # here is trusted by the dispatcher and exec'd - nothing has checked it
            # since the INSERT, and the INSERT didn't check it either ######
            cursor.execute(
                f"""SELECT lock_name, command FROM {ENCODING_QUEUE_TABLE}
                    WHERE pid IS NULL ORDER BY rowid LIMIT ?""",
                (limit,),
            )
            return cursor.fetchall()

    def mark_running(self, lock_name: str, pid: int) -> None:
        """Record that this job has been spawned. A non-NULL pid is what
        keeps poll_pending() from handing the same job out twice."""
        with SQLite(self.dbname) as cursor:
            cursor.execute(
                f"UPDATE {ENCODING_QUEUE_TABLE} SET pid = ? WHERE lock_name = ?",
                (pid, lock_name),
            )

    def delete(self, lock_name: str) -> None:
        """Remove the job row. Called when the process returns (any exit
        code) and on dispatch-time failures - a pure queue keeps nothing
        about a job it is done with. No-op if the row is already gone."""
        with SQLite(self.dbname) as cursor:
            cursor.execute(
                f"DELETE FROM {ENCODING_QUEUE_TABLE} WHERE lock_name = ?",
                (lock_name,),
            )

    def find(self, lock_name: str) -> t.Optional[sqlite3.Row]:
        """The job row for lock_name, or None. Any row means queued or
        running - that's the whole state space."""
        with SQLite(self.dbname) as cursor:
            cursor.execute(
                f"SELECT lock_name, command, pid FROM {ENCODING_QUEUE_TABLE} WHERE lock_name = ?",
                (lock_name,),
            )
            return cursor.fetchone()


# ---------------------------------------------------------------------------
# EncodingExecutor - the execution backend. LocalSubprocessExecutor today;
# a Fargate/Lambda-backed executor would satisfy spawn()/wait().
# ---------------------------------------------------------------------------

class LocalSubprocessExecutor:
    def spawn(self, command: t.List[str]) -> subprocess.Popen:
        # ###### SECURITY TODO (see banner near top of module): `command` is run
        # exactly as given. List form (no shell=True) limits it to "exec this
        # binary with these args" - still arbitrary code execution ######
        return subprocess.Popen(command)

    def wait(self, process: subprocess.Popen) -> int:
        """Blocks until `process` exits, returning its real exit code.
        This object called Popen() itself in spawn(), so it's the true
        parent - wait() here is guaranteed a real exit code, unlike a
        separate watcher process trying to inspect a child it didn't
        fork."""
        return process.wait()


# ---------------------------------------------------------------------------
# Module-level defaults + the interface EncodingManager calls.
#
# One dispatcher, one queue, for the whole app - same reasoning as
# cachedb.py's module-level functions: there's no case for multiple
# instances of "the" encoding queue, so this stays plain functions over a
# module-level default, not a class you'd instantiate.
# ---------------------------------------------------------------------------

_queue = SqliteEncodingQueue()


def lock_encoding(lock_name: str, command: t.List[str]) -> None:
    """Claim the queue slot for this video and persist the ffmpeg command
    to run for it. Raises EncodingAlreadyInProgressError if a job for
    lock_name is already queued or running."""
    # ###### SECURITY TODO (see banner): `command` is handed straight to the
    # queue for persistence and later verbatim execution ######
    _queue.enqueue(lock_name, command)


def update_lock(lock_name: str, process_id: int) -> None:
    """Record the pid of the encoding process for lock_name. The
    dispatcher (below) calls this itself once it spawns a job -
    EncodingManager no longer spawns ffmpeg itself, so it no longer calls
    this directly, but it stays part of the interface."""
    _queue.mark_running(lock_name, process_id)


def in_progress(lock_name: str) -> bool:
    """True if an ABR encode for lock_name is queued or running. It's just
    "does a row exist" - a claimed-but-not-yet-spawned row counts, because
    the point of the claim is to stop a second caller requesting a
    duplicate encode, and that's true the instant the row is written."""
    return _queue.find(lock_name) is not None


# ---------------------------------------------------------------------------
# The dispatcher: a small bounded worker pool, driven by a gunicorn
# master-hook thread.
# ---------------------------------------------------------------------------

def _configure_file_logging(log_file: str) -> None:
    """Attach a dedicated file handler to this module's logger, so
    encoding job status actually lands in the configured encoding_log
    file. Deliberately NOT routed through casterpak/__init__.py's
    setup_gunicorn_logging (which replaces a logger's handlers with
    gunicorn's own, sending it to error_log instead) - the whole point of
    a dedicated encoding_log is a file a human can tail for just encoding
    job status, so this attaches its own FileHandler and keeps it."""
    fh = logging.FileHandler(log_file)
    formatter = logging.Formatter(
        fmt='[%(asctime)s] [%(levelname)s] in casterpak-encoding: %(message)s'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.setLevel(logging.INFO)


def _supervise(queue: SqliteEncodingQueue, executor: LocalSubprocessExecutor,
               active: t.Dict[str, threading.Thread], active_lock: threading.Lock,
               lock_name: str, process) -> None:
    """Wait for one encoding child to exit, log how it went, delete its
    queue row, and drop it from the in-memory `active` set. Runs on its
    own thread, one per dispatched job.

    Module-level (rather than a closure defined inside _dispatch_once's
    loop) so the thread target is a plain named function with every input
    passed explicitly via Thread(args=...) - no per-iteration function
    object, and no loop-variable-capture footguns to reason about."""
    exit_code = executor.wait(process)
    if exit_code == 0:
        logger.info(f"encoding job for {lock_name} complete (pid {process.pid})")
    else:
        logger.error(
            f"encoding job for {lock_name} failed with exit code {exit_code} (pid {process.pid})"
        )
    # Pure queue: the job is done, so the row goes - regardless of how it exited.
    queue.delete(lock_name)
    with active_lock:
        del active[lock_name]


def _dispatch_once(queue: SqliteEncodingQueue, executor: LocalSubprocessExecutor,
                    active: t.Dict[str, threading.Thread], active_lock: threading.Lock,
                    pool_size: int) -> None:
    """One pass of the dispatch loop: claim room in the pool, pull that
    many pending jobs, spawn each one, and hand each off to its own
    _supervise() thread to wait() on."""
    with active_lock:
        capacity = pool_size - len(active)
    if capacity <= 0:
        return

    for job in queue.poll_pending(limit=capacity):
        lock_name = job['lock_name']
        with active_lock:
            if lock_name in active:
                continue

        try:
            # ###### SECURITY TODO (see banner near top of module): this is an
            # argv list that came back out of sqlite and is about to be exec'd ######
            command = json.loads(job['command'])
        except (TypeError, ValueError) as e:
            logger.error(f"encoding job {lock_name!r} has an unreadable command, dropping it: {e}")
            queue.delete(lock_name)
            continue

        try:
            # ###### SECURITY TODO (see banner): spawns whatever argv the DB row held ######
            process = executor.spawn(command)
        except OSError as e:
            logger.error(f"failed to spawn encoding job {lock_name!r}, dropping it: {e}")
            queue.delete(lock_name)
            continue

        logger.info(f"dispatching encoding job for {lock_name} (pid {process.pid})")
        queue.mark_running(lock_name, process.pid)

        thread = threading.Thread(
            target=_supervise,
            args=(queue, executor, active, active_lock, lock_name, process),
            daemon=True,
        )
        with active_lock:
            active[lock_name] = thread
        thread.start()


def start_encoding_dispatcher(poll_interval: int = 5, pool_size: int = 2,
                               dbname: str = DB_PATH, server=None) -> None:
    """
    Starts the background dispatcher thread. Meant to be called from
    gunicorn's on_starting hook (see gunicorn.conf.py), the same as
    cleanup.start_maintenance_loop() - runs once in the gunicorn MASTER
    process, before workers fork.

    The dispatcher polls the queue table for unclaimed jobs (pid IS NULL),
    spawns up to `pool_size` of them at once via LocalSubprocessExecutor,
    and supervises each one on its own thread so it can wait() on the
    child, log a real exit code, and delete the finished row.
    """
    app_config = get_config()
    log_file = app_config.get('logging', 'encoding_log', fallback='/var/log/casterpak.encoding.log')
    _configure_file_logging(log_file)

    initialize_encoding_db(dbname)

    queue = SqliteEncodingQueue(dbname)
    executor = LocalSubprocessExecutor()
    active: t.Dict[str, threading.Thread] = {}
    active_lock = threading.Lock()

    def loop():
        if server:
            server.log.info(
                f"Encoding: dispatcher thread started - polling every {poll_interval}s, "
                f"up to {pool_size} concurrent encodes."
            )
        logger.info(f"dispatcher started - poll_interval={poll_interval}s pool_size={pool_size}")
        while True:
            try:
                _dispatch_once(queue, executor, active, active_lock, pool_size)
                jitter = random.uniform(0, 1)
                time.sleep(poll_interval + jitter)
            except Exception as e:
                logger.error(f"dispatcher loop encountered an error: {e}")
                if server:
                    server.log.error(f"Encoding: dispatcher loop encountered an error: {e}")
                time.sleep(30)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
