#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE

# ## TODO: [CasterPak 0.8.x Refactor] - Database Initialization & Concurrency
# 1. Decouple Schema Creation: Move 'CREATE TABLE IF NOT EXISTS' out of the 
#    request-level connection loop. It causes unnecessary locking in Docker.
# 2. Permanent WAL Mode: Run 'PRAGMA journal_mode=WAL;' once during a dedicated 
#    initialization phase (e.g., in app.py before Gunicorn forks).
# 3. Connection Tuning: Ensure the SQLite context manager remains 'lean'—only 
#    handling cursor yields and commits. Increase timeout to 10.0s for 
#    containerized I/O overhead.
# 4. Bootstrap Logic: Create a 'db.initialize()' method to be called once at 
#    process start to handle items 1 & 2.


from typing import Iterable
import datetime
import sqlite3
import logging

logger = logging.getLogger("casterpak cleanup")

# cache names
SEGMENT_FILE_CACHE = 'segmentfile'
INPUT_FILE_CACHE = 'inputfile'

def initialize_cache_db(dbname: str = 'cacheDB.db'):
    """Initialize the cache database with the necessary tables and WAL mode.
       This should be called once at application startup before any requests are handled.
    """
    with SQLite(dbname) as cursor:
        # Enable Write-Ahead Logging for better concurrency
        cursor.execute("PRAGMA journal_mode=WAL;")
        logger.debug(f"Set journal_mode to WAL for database {dbname}")

        # Create tables for different caches if they don't exist
        for cache_name in [SEGMENT_FILE_CACHE, INPUT_FILE_CACHE]:
            table_name = ''.join(c for c in cache_name if c.isalnum())
            create_query = f"""CREATE TABLE IF NOT EXISTS {table_name} (
                               filename text PRIMARY KEY,
                               timestamp int NOT NULL);
                             """
            cursor.execute(create_query)
            logger.debug(f"Ensured table '{table_name}' exists in database {dbname}")

class SQLite(object):
    def __init__(self, file='sqlite.db'):
        self.file = file

    def __enter__(self):
        ## TODO: handle connect timeout to avoid locking
        self.conn = sqlite3.connect(self.file)  #timeout=5.0)
        self.conn.row_factory = sqlite3.Row

        return self.conn.cursor()

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.commit()
        self.conn.close()


class CacheDB(object):
    def __init__(self, dbname: str = 'cacheDB.db', cache_name: str = None) -> None:
        """create a new instance of a CacheDB
           in the case of holding multiple caches (like input file cache and output file cache)
           a 'cache_name' can be passed to differentiate different caches
        """
        self.table = None
        self.dbname = dbname

        if cache_name is None:
            self.table = "default_cache"
        else:
            self.table = ''.join(c for c in cache_name if c.isalnum())
            if self.table != cache_name:
                logger.warning(f"cache name {cache_name} sanitized to {self.table}")

        ## TODO Check if table exists, and if not, run db initialize.

    def addrecord(self, filename: str = None, timestamp: int = None) -> None:
        if filename is None:
            raise ValueError('filename must be specified to add a cache record')

        if timestamp is None:
            timestamp = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

        query = f"""INSERT INTO {self.table}
                    VALUES(?, ?)
                    ON CONFLICT(filename) DO UPDATE SET timestamp=excluded.timestamp
                 """

        with SQLite(self.dbname) as cursor:
            cursor.execute(query, (filename, timestamp))

    def find(self, age_in_minutes: int) -> Iterable[str]:
        then = int(datetime.datetime.now(datetime.timezone.utc).timestamp()) - age_in_minutes*60

        with SQLite(self.dbname) as cursor:
            cursor.execute(f"SELECT filename FROM {self.table} WHERE timestamp < ?", (then,))
            return [row[0] for row in cursor.fetchall()]

    find_expired = find

    def get_oldest(self, num: int) -> Iterable[str]:
        """ Get the 'num' oldest files from the cache """
        with SQLite(self.dbname) as cursor:
            cursor.execute(f"SELECT filename FROM {self.table} order by timestamp limit {num} ")
            return [row[0] for row in cursor.fetchall()]

    def delrecord(self, filename: str) -> None:
        """Remove cache record for 'filename'"""
        with SQLite(self.dbname) as cursor:
            cursor.execute(f"DELETE FROM {self.table} WHERE filename == ?", (filename,))
