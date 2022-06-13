import typing as t
import os
import shutil
import logging
import config

from urllib.parse import urljoin
from bento4.mp4utils import Mp42Hls

import cachedb
logger = logging.getLogger('vodhls')


class EncodingError(Exception):
    """ this error says something in the encoding binaries went wrong
    """
    pass


class ConfigurationError(Exception):
    pass


class OptionsConfig(object):
    """ This is a basic class that turns a dictionary into an object,
        it's job is to impersonate an optparse.OptionParser instance.
        We end up passing an instance of this to Mp42Hls
    """
    def __init__(self, config_dict):
        self.base_config = config_dict

    def __getattr__(self, item):
        return self.base_config[item]


class VODHLSManager(object):
    config = config.get_config()
    db = cachedb.CacheDB(cache_name=cachedb.INPUT_FILE_CACHE)

    def __init__(self, filename):
        self.base_url = ''

        # always remember that the input filename for mp4 file
        # becomes the output directory name for the hls files
        self.filename = filename

        try:
            os.stat(self.source_file)
        except FileNotFoundError:
            logger.info(f'{self.source_file} not found')
            raise

        # are we caching input files?
        if self.config['cache'].getboolean('cache_input'):
            try:
                os.stat(self.cached_filename)
            except FileNotFoundError:
                logger.debug(f"Input File cache miss for {self.cached_filename}")
                self.copy_and_cache()
            finally:
                self.process_file = self.cached_filename
                self.db.addrecord(filename=self.filename, timestamp=None)

        # No Input File Caching
        else:
            self.process_file = self.source_file

        logger.info(f"vldhls manager created for {self.filename}")

    def create(self) -> t.Union[os.PathLike, str]:
        """
        Create the HLS manifest file and all segments in the configured location

        :return:
        a path to the output HLS child manifest file (.m3u8)
        """

        hls_config = {
            'exec_dir': self.config['bento4']['binaryPath'],
            'debug': True,
            'verbose': False,
        }

        kwargs = {
            'index_filename': self.output_manifest_filename,
            'segment_filename_template': os.path.join(self.output_dir, 'segment-%d.ts'),
            'segment_url_template': urljoin(self.base_url, 'segment-%d.ts'),
            'segment_duration': "10",
            'allow-cache': True,
        }

        options = OptionsConfig(hls_config)

        if not os.path.isdir(self.output_dir):
            self.make_segment_dir()

        try:
            Mp42Hls(options, self.process_file, **kwargs)
        except Exception:
            logger.exception("Error creating segment files")
            raise EncodingError

        return self.output_manifest_filename

    @property
    def source_file(self) -> t.Union[os.PathLike, str]:
        try:
            path = self.config['input']['videoParentPath']
        except KeyError:
            msg = "videoParentPath not configured in casterpak config.ini"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.filename)

    @property
    def output_dir(self) -> t.Union[os.PathLike, str]:
        """
        :return:  the directory name that will contain the child playlist .m3u8 and segments
        This is the full path to the specific hls stream of the input file.
        """
        try:
            path = self.config['output']['segmentParentPath']
        except KeyError:
            msg = "segmentParentPath not configured in casterpak config.ini"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.filename)

    @property
    def cached_filename(self) -> t.Union[os.PathLike, str]:
        try:
            path = self.config['input']['VideoCachePath']
        except KeyError:
            msg = "VideoCachePath not configured in casterpak config.ini"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.filename)

    @property
    def output_manifest_filename(self) -> t.Union[os.PathLike, str]:
        try:
            filename = self.config['output']['childManifestFilename']
        except KeyError:
            msg = "childManifestFilename not configured in casterpak config.ini"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(self.output_dir, filename)

    def copy_and_cache(self):
        logger.debug(f"copy {self.source_file}, {self.cached_filename}")
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)
        shutil.copy(self.source_file, self.cached_filename)

    def set_baseurl(self, baseurl):
        self.base_url = baseurl

    def make_segment_dir(self) -> None:

        if not os.path.isdir(self.config['output']['segmentParentPath']):
            # configuration is wrong.  This path should always exist.
            logger.error(f"The configured segment directory {self.config['output']['segmentParentPath']} doesn't exist")
            raise FileNotFoundError

        logger.debug(f"creating new segment directory {os.path.join(self.output_dir)} ")
        os.makedirs(os.path.join(self.output_dir))

    def manifest_exists(self) -> bool:
        try:
            os.stat(self.output_manifest_filename)
        except FileNotFoundError:
            return False
        return True

    def segment_exists(self, segment_filename: t.Union[os.PathLike, str]) -> bool:
        """
        :param segment_filename: a filename of a segment, (not a full path).
           eg: 'segment-169.ts
        :return: bool - True if the file already exists on the filesystem
        """
        segment_path = os.path.join(self.output_dir, segment_filename)

        try:
            logger.debug(f"stat: {segment_path}")
            os.stat(segment_path)
        except FileNotFoundError:
            return False
        return True





