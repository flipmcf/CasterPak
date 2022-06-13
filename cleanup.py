import config
import cachedb
import os
import shutil
import sys
import logging

config = config.get_config()
logger = logging.getLogger('CasterPak-cleanup')

if config.get('application', 'debug', fallback=False):
    logging.basicConfig(level=logging.DEBUG)


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

        # and try to remove the parent directories
        path = os.path.split(file)
        empty: bool = True
        logger.debug("cleaning empty parent directories")
        while empty and len(path[0]):
            parent_dir = os.path.join(self.output_dir, path[0])
            try:
                logger.debug(f"rmdir {parent_dir}")
                os.rmdir(parent_dir)
            except OSError:
                logger.debug(f"{parent_dir} not empty, done")
                # directory not empty
                empty = False

            path = os.path.split(path[0])

    def delete_input(self, file):
        logger.debug(f"asked to delete input file {file}")

        delete_file = os.path.join(self.input_dir, file)
        logger.debug(f"removing {delete_file}")
        try:
            os.remove(delete_file)
        except FileNotFoundError:
            logger.debug(f"{delete_file} not found")
        self.input_file_db.delrecord(file)

        # and try to remove the parent directories
        path = os.path.split(file)
        empty: bool = True
        logger.debug("cleaning empty parent directories")
        while empty and len(path[0]):
            parent_dir = os.path.join(self.input_dir, path[0])
            try:
                logger.debug(f"rmdir {parent_dir}")
                os.rmdir(parent_dir)
            except OSError:
                logger.debug(f"{parent_dir} not empty, done")
                # directory not empty
                empty = False

            path = os.path.split(path[0])


if __name__ == "__main__":
    logger.info("running CasterPak cleanup")
    cleaner = CacheCleaner()
    try:
        sys.exit(cleaner.clean())
    except Exception as err:
        logger.error(f'CasterPak exited with Error: \n {err}')
        sys.exit(1)
