from tinydb import TinyDB, Query


import datetime

class DB(object):
    def __init__(self):
        self.db = TinyDB('cacheDB.json')

    def addrecord(self, filename=None,timestamp=None):
        if timestamp is None:
            timestamp = datetime.datetime.now(datetime.timezone.utc)

        self.db.insert({'f': filename, 't': int(timestamp.timestamp())})

    def find(self, age_in_minutes):
        Files = Query()

        def test_func(s):
            return s < (int(datetime.datetime.now().timestamp()) - age_in_minutes*60)

        return self.db.search(Files.t.test(test_func))

    def delrecord(self, filename):
        Files = Query()
        return self.db.remove(Files.f == filename)

if __name__ == "__main__":

    db = DB()
    db.addrecord('/foo/bar')
    db.addrecord('/foo/biz', datetime.datetime(2022,4,25,12,21,2))
    db.addrecord('/foo/biz/old', datetime.datetime(2022,4,20,12,21,2))
    db.addrecord('/foo/biz/really_old', datetime.datetime(2022, 3, 20, 12, 21, 2))

    #3 days old = 60*24*3


    print(db.find(60*24*3))

    count = db.delrecord('/foo/biz/really_old')
    print(f"removed {count} records")

