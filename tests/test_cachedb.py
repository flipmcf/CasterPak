#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#BSD 3-Clause License
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
import sqlite3
import unittest
import datetime

import cachedb


class InitializeDBTestCase(unittest.TestCase):
    db_filename = 'test_init.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_initialize_cache_db(self):
        """Tests if the database and tables are created."""
        cachedb.initialize_cache_db(self.db_filename)
        self.assertTrue(os.path.exists(self.db_filename))

        with sqlite3.connect(self.db_filename) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            self.assertIn(cachedb.SEGMENT_FILE_CACHE, tables)
            self.assertIn(cachedb.INPUT_FILE_CACHE, tables)


class CacheDBTestCase(unittest.TestCase):
    db_filename = 'test_CacheDB.db'

     # The CacheDB class requires the table to exist.
    # we will use the built-in 'INPUT_FILE_CACHE" name
    cache_name = cachedb.SEGMENT_FILE_CACHE

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

        self.testclass = cachedb.CacheDB(dbname=self.db_filename, cache_name=self.cache_name)
        cachedb.initialize_cache_db(self.db_filename)

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_add_and_get_record(self):
        """Test adding a record and retrieving it."""
        filename = "test_file.ts"
        self.testclass.addrecord(filename)

        with cachedb.SQLite(self.db_filename) as cursor:
            cursor.execute(f"SELECT filename, timestamp FROM {self.cache_name} WHERE filename=?", (filename,))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['filename'], filename)
            # Check if timestamp is recent
            self.assertAlmostEqual(row['timestamp'], datetime.datetime.now(datetime.timezone.utc).timestamp(), delta=5)

    def test_update_record(self):
        """Test if adding an existing record updates its timestamp."""
        filename = "test_file_update.ts"
        original_timestamp = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).timestamp())
        
        self.testclass.addrecord(filename, timestamp=original_timestamp)
        
        # Now update it
        new_timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        self.testclass.addrecord(filename, timestamp=new_timestamp)

        with cachedb.SQLite(self.db_filename) as cursor:
            cursor.execute(f"SELECT timestamp FROM {self.cache_name} WHERE filename=?", (filename,))
            row = cursor.fetchone()
            self.assertEqual(row[0], new_timestamp)


    def test_find_expired(self):
        """Test finding expired records."""
        file_new = "new_file.ts"
        file_old = "old_file.ts"
        
        self.testclass.addrecord(file_new) # Add with current time
        
        old_timestamp = int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).timestamp())
        self.testclass.addrecord(file_old, timestamp=old_timestamp)

        expired_files = self.testclass.find(age_in_minutes=2)
        self.assertIn(file_old, expired_files)
        self.assertNotIn(file_new, expired_files)

    def test_delrecord(self):
        """Test deleting a record."""
        filename = "test_file_to_delete.ts"
        self.testclass.addrecord(filename)
        
        # Make sure it is there
        with cachedb.SQLite(self.db_filename) as cursor:
             cursor.execute(f"SELECT filename FROM {self.cache_name} WHERE filename=?", (filename,))
             self.assertIsNotNone(cursor.fetchone())

        self.testclass.delrecord(filename)

        # Now it should be gone
        with cachedb.SQLite(self.db_filename) as cursor:
            cursor.execute(f"SELECT filename FROM {self.cache_name} WHERE filename=?", (filename,))
            self.assertIsNone(cursor.fetchone())

    def test_get_oldest(self):
        """Test retrieving the oldest records."""
        files = ["file1.ts", "file2.ts", "file3.ts"]
        timestamps = [
            int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=3)).timestamp()),
            int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)).timestamp()),
            int((datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=2)).timestamp()),
        ]

        for f, t in zip(files, timestamps):
            self.testclass.addrecord(f, t)
        
        oldest_files = self.testclass.get_oldest(2)
        
        self.assertEqual(len(oldest_files), 2)
        self.assertIn(files[0], oldest_files) # oldest
        self.assertIn(files[2], oldest_files) # second oldest
        self.assertNotIn(files[1], oldest_files) # newest


class MultipleCacheTestCase(unittest.TestCase):
    db_filename = 'test_multi_cache.db'

    def setUp(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)
        cachedb.initialize_cache_db(self.db_filename)
        self.segment_cache = cachedb.CacheDB(dbname=self.db_filename, cache_name=cachedb.SEGMENT_FILE_CACHE)
        self.input_cache = cachedb.CacheDB(dbname=self.db_filename, cache_name=cachedb.INPUT_FILE_CACHE)

    def tearDown(self):
        if os.path.exists(self.db_filename):
            os.remove(self.db_filename)

    def test_isolated_caches(self):
        """Tests that two cache instances do not interfere with each other."""
        segment_file = "segment1.ts"
        input_file = "input.mp4"

        self.segment_cache.addrecord(segment_file)
        self.input_cache.addrecord(input_file)

        # Check segment cache
        with cachedb.SQLite(self.db_filename) as cursor:
            cursor.execute(f"SELECT filename FROM {cachedb.SEGMENT_FILE_CACHE}")
            files = [row[0] for row in cursor.fetchall()]
            self.assertIn(segment_file, files)
            self.assertNotIn(input_file, files)
        
        # Check input cache
        with cachedb.SQLite(self.db_filename) as cursor:
            cursor.execute(f"SELECT filename FROM {cachedb.INPUT_FILE_CACHE}")
            files = [row[0] for row in cursor.fetchall()]
            self.assertIn(input_file, files)
            self.assertNotIn(segment_file, files)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(InitializeDBTestCase))
    suite.addTest(unittest.makeSuite(CacheDBTestCase))
    suite.addTest(unittest.makeSuite(MultipleCacheTestCase))
    return suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner()
    runner.run(suite())