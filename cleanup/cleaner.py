#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE

# cleanup/cleaner.py
import sys
import os
import logging
import typing as t
import subprocess
import shutil


import config
import cachedb

app_config = config.get_config()
logger = logging.getLogger('CasterPak-cleanup')

if app_config.get('application', 'debug', fallback=False):
    logger.setLevel(logging.DEBUG)


def run_cleanup():
    logger.info("running CasterPak cleanup")
    cleaner = CacheCleaner()
    try:
        cleaner.clean()
    except Exception as err:
        logger.error(f'cleanup exited with Error: \n {err}')


def get_disk_usage(path: t.Union[os.PathLike, str]) -> int:
    """ get the total file size of the directory."""

    if not os.path.exists(path):
        logger.debug(f"directory {path} does not exist, returning 0 usage")
        return 0
    # This will only work on posix / linux - but that's ok.  It's efficient.
    size = subprocess.check_output(['du', '-BM', '--max-depth=0', path]).split()[0]

    # size is a string like '120M' for 120 megabytes.
    # strip off that 'M' and return an integer
    ## Don't fix this - the subprocess call forces Megabytes
    return int(size[:-1])


class CacheCleaner(object):
    def __init__(self):
        ## TODO - scan the filesystem for files that do no exist in the cache_db, and remove them.
        output_config = app_config['output']
        input_config = app_config['input']
        cache_config = app_config['cache']

        try:
            self.output_dir = output_config['segmentParentPath']
        except KeyError:
            logger.critical("No [output] segmentParentPath configured")

        try:
            self.input_dir = input_config['videoCachePath']
        except KeyError:
            logger.critical("No [input] videoCachePath configured")

        self.segment_file_age = cache_config.getint('segment_file_age', fallback=4320)
        self.segment_cache_size = cache_config.getint('segment_file_cache_size', fallback=16384)
        self.segment_cache_threshold = cache_config.getint('segment_file_cache_limit', fallback=90)
        self.input_file_age = cache_config.getint('input_file_age', fallback=8640)
        self.input_cache_size = cache_config.getint('input_file_cache_size', fallback=8192)
        self.input_cache_threshold = cache_config.getint('input_file_cache_limit', fallback=90)

        self.segment_db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
        self.input_file_db = cachedb.CacheDB(cache_name=cachedb.INPUT_FILE_CACHE)

    def clean(self):
        files = self.get_old_segment_files()
        logger.debug(f"segment files to clean: {files}")
        for file in files:
            self.delete_segment(file)

        files = self.get_old_input_files()
        logger.debug(f"input files to clean {files}")
        for file in files:
            self.delete_input(file)

        while self.segment_cache_threshold_reached:
            logger.warning("segment cache threshold reached. consider increasing segment cache size")
            file = self.get_oldest_segment_file()
            self.delete_segment(file)

        while self.input_cache_threshold_reached:
            logger.warning("input file cache threshold reached. consider increasing input file cache size")
            file = self.get_oldest_input_file()
            self.delete_input(file)

        return 0

    def get_old_segment_files(self):
        return self.segment_db.find(self.segment_file_age)

    def get_old_input_files(self):
        return self.input_file_db.find(self.input_file_age)

    def get_oldest_segment_file(self) -> str:
        result = self.segment_db.get_oldest(num=1)
        return result[0]

    def get_oldest_input_file(self) -> str:
        result = self.input_file_db.get_oldest(num=1)
        return result[0]

    def delete_segment(self, file):
        logger.debug(f"asked to delete segments {file}")

        segment_dir = os.path.join(self.output_dir, file)
        logger.debug(f"pruning {segment_dir}")
        try:
            shutil.rmtree(segment_dir)
        except FileNotFoundError:
            logger.debug(f"{segment_dir} not found")
        self.segment_db.delrecord(file)

        parent_dir = os.path.dirname(file)
        self.clean_empty_parents(self.output_dir, parent_dir)

    def delete_input(self, file):
        logger.debug(f"asked to delete input file {file}")

        delete_file = os.path.join(self.input_dir, file)
        logger.debug(f"removing {delete_file}")
        try:
            os.remove(delete_file)
        except (FileNotFoundError, NotADirectoryError) as e:
            logger.debug(f"{delete_file} not found")
        self.input_file_db.delrecord(file)

        parent_dir = os.path.dirname(file)
        self.clean_empty_parents(self.input_dir, parent_dir)

    @property
    def segment_cache_threshold_reached(self) -> bool:
        """ Return true if the output segment cache is at it's configured size limit, False otherwise"""
        usage = get_disk_usage(self.output_dir)
        pct_full = usage / self.segment_cache_size * 100
        logger.debug(f"segment cache is {usage}M - {pct_full}% full")

        if pct_full > self.segment_cache_threshold:
            return True
        return False

    @property
    def input_cache_threshold_reached(self) -> bool:
        """ Return true if the input cache is at it's configured size limit, False otherwise"""
        usage = get_disk_usage(self.input_dir)
        pct_full = usage / self.input_cache_size * 100
        logger.debug(f"input cache is {usage}M - {pct_full}% full")

        if pct_full > self.input_cache_threshold:
            return True
        return False

    @staticmethod
    def clean_empty_parents(dir_root, sub_dir):
        """

        :param dir_root: directory root to delete empty dirs up to.
        only subdirectories of dir_root will be removed, dir_root will never be removed

        :param sub_dir:  directory path to check if empty, and remove directory if it is empty

        :return: None

        if sub_dir is found empty, it will be removed.
        If it's removed, repeat the process on each parent until 'dir_root' is reached.
        This ensures that empty directories don't clog up the cache.
        """
        empty: bool = True  # Assume empty to always enter the loop at least once - 'do while'
        logger.debug("cleaning empty directories")
        while empty and len(sub_dir):
            dir_path = os.path.join(dir_root, sub_dir)
            logger.debug(f"rmdir {dir_path}")
            try:
                os.rmdir(dir_path)
            except OSError:
                logger.debug(f"{dir_path} not empty, done")
                empty = False
            else:
                sub_dir = os.path.dirname(sub_dir)


if __name__ == "__main__":


    # When run as a standalone script, configure a file handler for logging.


    log_file = app_config.get('logging', 'cache_log', fallback='/var/log/casterpak.cache.log')
    fh = logging.FileHandler(log_file)
    formatter = logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] in casterpak-cleanup: %(message)s')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.setLevel(logging.INFO) # Ensure messages are captured

    run_cleanup()

