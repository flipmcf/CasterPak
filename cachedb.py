import datetime
from tinydb import TinyDB, Query


class CacheDB(object):
    def __init__(self, dbname='cacheDB.json'):
        self.db = TinyDB(dbname)

    def addrecord(self, filename=None,timestamp=None):
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

