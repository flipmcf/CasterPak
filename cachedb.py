from typing import Iterable
import datetime
import sqlite3
import logging

logger = logging.getLogger("casterpak cleanup")

# cache names
SEGMENT_FILE_CACHE = None
INPUT_FILE_CACHE = 'inputfile'


class SQLite(object):
    def __init__(self, file='sqlite.db'):
        self.file=file

    def __enter__(self):
        self.conn = sqlite3.connect(self.file)
        self.conn.row_factory = sqlite3.Row
        return self.conn.cursor()

    def __exit__(self, exc_type, exc_value, traceback):
        self.conn.commit()
        self.conn.close()


class CacheDB(object):
    def __init__(self, dbname: str = 'cacheDB.db', cache_name: str = None) -> None:
        """create a new instance of a CacheDB
           in the case of holding multiple caches (like input file cache and output file cache)
           a 'cachetype' can be passed to differentiate different caches
        """
        self.table = None
        self.dbname = dbname

        if cache_name is None:
            self.table = "default_table"
        else:
            self.table = ''.join(c for c in cache_name if c.isalnum())
            if self.table != cache_name:
                logger.warning(f"cache name {cache_name} sanitized to {self.table}")

        create_query = f"""CREATE TABLE IF NOT EXISTS {self.table} (
                           filename text PRIMARY KEY,
                           timestamp int NOT NULL);
                         """
        with SQLite(self.dbname) as cursor:
            cursor.execute(create_query)

    def addrecord(self, filename: str = None, timestamp: str = None) -> None:
        if filename is None:
            raise ValueError('filename must be specified to add a cache record')

        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        query = f"""INSERT INTO {self.table}
                    VALUES(?, ?)
                    ON CONFLICT(filename) DO UPDATE SET timestamp=excluded.timestamp
                 """

        with SQLite(self.dbname) as cursor:
            cursor.execute(query, (filename, timestamp))

    def find(self, age_in_minutes: int) -> Iterable[str]:
        then = int(datetime.datetime.now().timestamp()) - age_in_minutes*60

        with SQLite(self.dbname) as cursor:
            cursor.execute(f"SELECT filename FROM {self.table} WHERE timestamp < ?", (then,))
            return [row[0] for row in cursor.fetchall()]

    def delrecord(self, filename: str) -> None:

        with SQLite(self.dbname) as cursor:
            cursor.execute("DELETE FROM {self.table} WHERE filename == ?", (filename,))
        

