from collections.abc import Iterator
import datetime
import sqlite3
from sqlite3 import Error


# cache names
SEGMENT_FILE_CACHE = None
INPUT_FILE_CACHE = 'inputfile'

from logging import getLogger

logger = getLogger("casterpak cleanup")

class CacheDB(object):
    def __init__(self, dbname: str = 'cacheDB.db', cache_name: str = None) -> None:
        """create a new instance of a CacheDB
           in the case of holding multiple caches (like input file cache and output file cache)
           a 'cachetype' can be passed to differentiate different caches
        """
        self.table = None
        self.db = sqlite3.connect(dbname,)

        if cache_name is None:
            self.table = "default"
        else:
            self.table = ''.join(c for c in cache_name if c.isalnum())
            if self.table != cache_name:
                logger.warning(f"cache name {cache_name} sanitized to {self.table}")

        create_query = f"""CREATE TABLE IF NOT EXISTS {self.table} (
                           filename text PRIMARY KEY,
                           timestamp int NOT NULL);
                         """

        self.db.execute(create_query)

    def addrecord(self, filename: str = None, timestamp: str = None) -> None:
        if filename is None:
            raise ValueError('filename must be specified to add a cache record')

        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        query = f"""INSERT INTO {self.table}
                    VALUES(?, ?)
                    ON CONFLICT(filename) DO UPDATE SET timestamp=excluded.timestamp
                 """
        self.db.execute(query, (filename, timestamp))

    def find(self, age_in_minutes: int) -> Iterator[str]:

        cursor = self.db.cursor()
        then = int(datetime.datetime.now().timestamp()) - age_in_minutes*60
        cursor.execute("SELECT filename FROM {self.table} WHERE timestamp < ?", (then,))

        return [row[0] for row in cursor.fetchall()]

    def delrecord(self, filename: str) -> None:
        cursor = self.db.cursor()
        cursor.execute("DELETE FROM {self.table} WHERE filename == ?", (filename,))
        

