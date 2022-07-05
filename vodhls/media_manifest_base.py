import typing as t
import os
import logging

from urllib.parse import urljoin
from bento4.mp4utils import Mp42Hls

import cachedb
from config import get_config

from . import EncodingError, ConfigurationError

logger = logging.getLogger('vodhls')


class OptionsConfig(object):
    """ This is a basic class that turns a dictionary into an object,
        it's job is to impersonate an optparse.OptionParser instance.
        We end up passing an instance of this to Mp42Hls
    """
    def __init__(self, config_dict):
        self.base_config = config_dict

    def __getattr__(self, item):
        try:
            return self.base_config[item]
        except KeyError:
            return None


class MediaManager_Base(object):
    """
        base class for media manifest segment managers / generators.
        These take a single mp4 file, break it into segments, and create a media manifest index file.
    """

    config = get_config()
    db = cachedb.CacheDB(cache_name=cachedb.INPUT_FILE_CACHE)

    def __init__(self, filename):
        self.base_url = ''

        # always remember that the input filename for mp4 file
        # becomes the output directory name for the hls files
        self.filename = filename

        #make a note to the cache database that the input file has been touched
        self.db.addrecord(filename=self.filename, timestamp=None)

    def fetch_and_cache(self):
        """ This is where the input file is moved to the local filesystem if necessary
        Override in base class as appropriate
        """
        raise NotImplementedError("Base Class Exception")

    def set_baseurl(self, baseurl) -> None:
        """
        :param baseurl: a base url to write to each segment file,
         making the manifest a collection of absolute url's to each segment

        """
        self.base_url = baseurl

    def manage_input_file(self) -> None:
        try:
            os.stat(self.input_file)
        except FileNotFoundError:
            logger.debug(f"Input File cache miss for {self.input_file}")
            self.fetch_and_cache()
        finally:
            self.db.addrecord(filename=self.filename, timestamp=None)

    process_input = manage_input_file

    def create(self) -> t.Union[os.PathLike, str]:
        """
        Create the media HLS manifest file and all segments in the configured location

        :return:
        a path to the output HLS media manifest file (.m3u8)
        """

        # make sure input file is available.
        self.manage_input_file()

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
            Mp42Hls(options, self.input_file, **kwargs)
        except Exception:
            logger.exception("Error creating segment files")
            raise EncodingError

        return self.output_manifest_filename

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

    def make_segment_dir(self) -> None:

        if not os.path.isdir(self.config['output']['segmentParentPath']):
            # configuration is wrong.  This path should always exist.
            logger.error(f"The configured segment directory {self.config['output']['segmentParentPath']} doesn't exist")
            raise FileNotFoundError

        logger.debug(f"creating new segment directory {os.path.join(self.output_dir)} ")
        os.makedirs(os.path.join(self.output_dir))

    @property
    def output_dir(self) -> t.Union[os.PathLike, str]:
        """
        :return:  the directory name that will contain the child playlist .m3u8 and segments
        This is the full path to the specific hls stream of the input file.
        """
        try:
            path = self.config['output']['segmentParentPath']
        except KeyError:
            msg = "segmentParentPath not configured in casterpak config.ini 'output' section"
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

    @property
    def cached_filename(self) -> t.Union[os.PathLike, str]:
        try:
            path = self.config['input']['VideoCachePath']
        except KeyError:
            msg = "VideoCachePath not configured in casterpak config.ini"
            logger.error(msg)
            raise ConfigurationError(msg)

        return os.path.join(path, self.filename)

    # More often than not, you are going to feed the file from the local cache to mp42hls
    @property
    def input_file(self) -> t.Union[os.PathLike, str]:
        return self.cached_filename

