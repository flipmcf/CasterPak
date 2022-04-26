import config
import cachedb
import os
import shutil
import sys
import logging
import applogging

config = config.get_config()
logger = logging.getLogger('CasterPak-cleanup')

if config.get('application', 'debug', fallback=False):
    logging.basicConfig(level=logging.DEBUG)


class CacheCleaner(object):
    def __init__(self):
        self.output_dir = config['output']['segmentParentPath']
        self.output_filename = config['output']['childManifestFilename']
        self.db = cachedb.CacheDB()

    def clean(self):
        files = self.get_old_files()
        logger.debug(f"files to clean: {files}")
        for file in files:
            self.delete(file)

        return 0

    def get_old_files(self):
        return self.db.find(int(config['cache']['age']))

    def delete(self, file):
        logger.debug(f"asked to delete {file}")

        segment_dir = os.path.join(self.output_dir, file)
        logger.debug(f"pruning {segment_dir}")
        try:
            shutil.rmtree(segment_dir)
        except FileNotFoundError:
            logger.debug(f"{segment_dir} not found")
        self.db.delrecord(file)

        # and try to remove the parent directories
        path = os.path.split(file)
        empty: bool = True
        logger.debug("cleaning empty parent directories")
        while empty and len(path[0]):
            parent_dir = os.path.join(self.output_dir,path[0])
            try:
                logger.debug(f"rmdir {parent_dir}")
                os.rmdir(parent_dir)
            except OSError:
                logger.debug(f"{parent_dir} not empty, done")
                #directory not empty
                empty = False

            path = os.path.split(path[0])


if __name__ == "__main__":
    logger.info("running CasterPak cleanup")
    cleaner = CacheCleaner()
    try:
        sys.exit(cleaner.clean())
    except Exception as err:
        logger.error(f'CasterPak exited with Error: \n {err}')
        raise
        sys.exit(1)
