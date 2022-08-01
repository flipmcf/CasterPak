import os
import unittest

import cachedb


class CacheDBTestCase(unittest.TestCase):
    db_filename = 'test_CacheDB.db'

    def setUp(self):
        self.testclass = cachedb.CacheDB(self.db_filename)

    def tearDown(self):
        self.testclass.db.close()
        os.remove(self.db_filename)

    def test_addrecord(self):
        pass

    def test_find(self):
        pass

    def test_delrecord(self):
        pass


def suite():
    suite = unittest.TestSuite()
    suite.addTest(CacheDBTestCase)
    return suite


if __name__ == "__main__":
    runner = unittest.TextTestRunner()
    runner.run(suite())

