#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Repo-wide pytest configuration and guards.

Being here also fixes pytest's rootdir at the repo root regardless of the
directory pytest is launched from.
"""
import pathlib

import pytest

_REPO_ROOT = pathlib.Path(__file__).parent

# cachedb.DB_PATH defaults to a relative "cacheDB.db", and config.py chdir's to
# the repo root on import, so a stray cache database always lands right here.
# Its mere presence makes green test runs lie: several route tests reach
# cachedb.CacheDB without any test having created the schema, and they only
# pass because a database with the tables happens to already be sitting in the
# tree (left by `./bin/python -m flask run`, an earlier crashed test run, etc).
# Refuse to run until it's gone.
_STRAY_DB_FILES = ("cacheDB.db", "cacheDB.db-wal", "cacheDB.db-shm")


def pytest_configure(config):
    stray = [name for name in _STRAY_DB_FILES if (_REPO_ROOT / name).exists()]
    if stray:
        found = ", ".join(str(_REPO_ROOT / name) for name in stray)
        removal = " ".join(f"'{_REPO_ROOT / name}'" for name in _STRAY_DB_FILES)
        raise pytest.UsageError(
            f"stray SQLite cache database in the repo tree: {found}\n"
            "It masks test-isolation bugs - tests that need the cachedb schema "
            "but never create it pass only because this file exists.\n"
            f"Remove it and re-run:  rm -f {removal}"
        )
