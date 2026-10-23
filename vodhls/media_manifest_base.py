#Copyright (c) 2026, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import typing as t
import os
import fcntl
import functools
import logging
import uuid

from contextlib import contextmanager
from urllib.parse import urljoin
from werkzeug.utils import safe_join
from bento4.mp4utils import Mp42Hls

import cachedb
from config import get_config
from pathsafety import InvalidPathError

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


@contextmanager
def get_fetch_lock(lock_path: t.Union[os.PathLike, str]):
    """
    Hold an exclusive flock on lock_path. Waiters sleep in flock() until it is released.
    The lock file is deleted on release. If a worker dies, the kernel releases its lock and
    the leftover file is reused and deleted by the next holder.
    """
    while True:
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        fcntl.flock(fd, fcntl.LOCK_EX)
        # While we waited, the holder may have deleted the file we locked, and a newcomer may
        # have created and locked a new one at the same path. Only the file at the path counts.
        try:
            same_file = os.fstat(fd).st_ino == os.stat(lock_path).st_ino
        except FileNotFoundError:
            same_file = False
        if same_file:
            break
        os.close(fd)

    try:
        yield
    finally:
        # unlink before releasing, so nobody can lock this file once we let go
        os.unlink(lock_path)
        os.close(fd)


@contextmanager
def atomic_write(destination: t.Union[os.PathLike, str]):
    """
    Yield a temporary path next to destination. If the body succeeds, the temporary file
    replaces destination in one rename, so a reader never sees a partial file.
    """
    tmp = f"{destination}.part-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    try:
        yield tmp
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def locked_fetch(fetch):
    """
    Decorate fetch_and_cache so concurrent requests for one video fetch it once.
    The others wait for the lock, find the file in the cache, and return.
    """
    @functools.wraps(fetch)
    def wrapper(self):
        os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)
        with get_fetch_lock(self.cached_filename + '.lock'):
            if os.path.exists(self.cached_filename):
                logger.debug(f"{self.cached_filename} was fetched while waiting for the lock")
                return
            fetch(self)
    return wrapper


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
        # becomes the name of the output directory
        # which will contain the segment files and media manifest
        self.filename = filename

    def fetch_and_cache(self):
        """ This is where the input file is moved to the local filesystem if necessary
        Override in base class as appropriate. Decorate the override with @locked_fetch
        and write the file through atomic_write(self.cached_filename).
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

        self.db.addrecord(filename=self.filename, timestamp=None)

    process_input = manage_input_file

    @property
    def segment_duration(self):
        try:
            return self.config['output']['segmentDuration']
        except KeyError:
            return '6'

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
            'segment_duration': str(self.segment_duration),
            'allow-cache': "YES",
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

        # Defense-in-depth: routes.py already validates self.filename before
        # it ever gets here (see pathsafety.py), so this should never
        # actually reject anything - but if it ever does, refuse to escape
        # segmentParentPath rather than silently joining an absolute path or
        # '..' segment onto it.
        joined = safe_join(path, self.filename)
        if joined is None:
            raise InvalidPathError(f"unsafe path: {self.filename!r} escapes {path!r}")
        return joined

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

