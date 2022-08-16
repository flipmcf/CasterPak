import config
import cachedb
import os
import shutil
import sys
import logging

config = config.get_config()
logger = logging.getLogger('CasterPak-cleanup')

if config.get('application', 'debug', fallback=False):
    logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('/var/log/casterpak.log')
formatter = logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] in casterpak-cleanup: %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


class CacheCleaner(object):
    def __init__(self):
        self.output_dir = config['output']['segmentParentPath']
        self.output_filename = config['output']['childManifestFilename']
        self.input_dir = config['input']['videoCachePath']
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

        return 0

    def get_old_segment_files(self):
        return self.segment_db.find(int(config['cache']['segment_file_age']))

    def get_old_input_files(self):
        return self.input_file_db.find(int(config['cache']['input_file_age']))

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
        except FileNotFoundError:
            logger.debug(f"{delete_file} not found")
        self.input_file_db.delrecord(file)

        parent_dir = os.path.dirname(file)
        self.clean_empty_parents(self.input_dir, parent_dir)

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
    logger.info("running CasterPak cleanup")
    cleaner = CacheCleaner()
    try:
        sys.exit(cleaner.clean())
    except Exception as err:
        logger.error(f'cleanup exited with Error: \n {err}')
        sys.exit(1)
