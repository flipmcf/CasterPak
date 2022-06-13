import datetime
from tinydb import TinyDB, Query

# cache names
SEGMENT_FILE_CACHE = None
INPUT_FILE_CACHE = 'inputfile'


class CacheDB(object):
    def __init__(self, dbname='cacheDB.json', cache_name=None):
        """create a new instance of a CacheDB
           in the case of holding multiple caches (like input file cache and output file cache)
           a 'cachetype' can be passed to differentiate different caches
        """
        db = TinyDB(dbname)
        if cache_name is None:
            self.db = db
        else:
            self.db = db.table(cache_name)

    def addrecord(self, filename=None, timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        Files = Query()
        self.db.upsert({'f': filename, 't': int(timestamp.timestamp())},
                       Files.f == filename)

    def find(self, age_in_minutes):
        Files = Query()

        def test_func(s):
            return s < (int(datetime.datetime.now().timestamp()) - age_in_minutes*60)

        rows = self.db.search(Files.t.test(test_func))

        return [row['f'] for row in rows]

    def delrecord(self, filename):
        Files = Query()
        return self.db.remove(Files.f == filename)

