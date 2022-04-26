import datetime
from tinydb import TinyDB, Query

class CacheDB(object):
    def __init__(self):
        self.db = TinyDB('cacheDB.json')

    def addrecord(self, filename=None,timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        File = Query()
        self.db.upsert({'f': filename, 't': int(timestamp.timestamp())},
                       File.f == filename)

    def find(self, age_in_minutes):
        Files = Query()

        def test_func(s):
            return s < (int(datetime.datetime.now().timestamp()) - age_in_minutes*60)

        return self.db.search(Files.t.test(test_func))

    def delrecord(self, filename):
        Files = Query()
        return self.db.remove(Files.f == filename)

