#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#BSD 3-Clause License
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import os
import unittest

import cachedb


class CacheDBTestCase(unittest.TestCase):
    db_filename = 'test_CacheDB.db'

    def setUp(self):
        self.testclass = cachedb.CacheDB(dbname=self.db_filename)

    def tearDown(self):
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

