#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import fcntl
import hashlib
import logging
import os
import typing as t
import uuid

from vodhls import ConfigurationError, InputFetchError
from vodhls.media_manifest_base import MediaManager_Base
import s3client
from pathsafety import validate_filename

logger = logging.getLogger('vodhls')

# S3 answers a missing key with one of these, depending on the call and on
# whether the caller may ListBucket (see fetch_and_cache).
_MISSING_CODES = {'404', 'NoSuchKey', 'NotFound'}


class MediaManager_s3(MediaManager_Base):
    """
    Implements S3-input based VODHLS Manager.

    A URL path maps to an object key by plain concatenation, the same way
    the filesystem input maps it onto videoParentPath:

        key = [s3] prefix + <path from the URL>

        prefix = 'videos/'           (in config.ini)
        URL    = /i/alice/clip.mp4/master.m3u8
        key    = videos/alice/clip.mp4

    S3 has no directories - '/' is just a character in the key - so there is
    nothing to create or walk; "directories" are simply shared key prefixes.

    Like http, S3 is slow and every read costs money, so the object is
    fetched ONCE into the local input cache (see MediaManager_Base) and
    everything after that - Bento4, ffmpeg, re-packaging - reads the local
    copy. The cleaner ages cached copies out like any other input file.
    """

    def __init__(self, filename):
        super(MediaManager_s3, self).__init__(filename)
        # Defense-in-depth, same as the filesystem manager: routes.py has
        # already validated this. S3 keys have no '..' semantics, but the
        # rule that a URL can never name anything outside its own prefix is
        # worth keeping identical across backends.
        # Validate EVERY '/'-separated segment of the whole string rather
        # than os.path.split()ing it: split() quietly collapses 'a//b.mp4'
        # to ('a', 'b.mp4'), and here the raw string becomes the S3 key, so
        # 'a//b' would name a different object than the path that passed.
        for segment in filename.split('/'):
            validate_filename(segment)
        logger.info(f"vodhls s3 manager for {self.source_uri}")

    # -- configuration ----------------------------------------------------

    def _opt(self, option, fallback=''):
        return s3client.s3_option(self.config, option, fallback)

    @property
    def bucket(self) -> str:
        return s3client.bucket_and_prefix(self.config)[0]

    @property
    def prefix(self) -> str:
        return s3client.bucket_and_prefix(self.config)[1]

    @property
    def source_key(self) -> str:
        return self.prefix + self.filename

    @property
    def source_uri(self) -> str:
        return f"s3://{self.bucket}/{self.source_key}"

    @property
    def client(self):
        return s3client.client_from_config(self.config)

    # -- fetching ---------------------------------------------------------

    def _lock_path(self) -> str:
        cache_root = self.config['input']['VideoCachePath']
        digest = hashlib.sha1(self.source_uri.encode()).hexdigest()
        return os.path.join(cache_root, '.locks', digest)

    def fetch_and_cache(self):
        """Download the object into the input cache.

        - Missing object -> FileNotFoundError, so routes.py answers 404 (and
          the CSMIL manager can skip a rendition that isn't there).
        - Anything else that goes wrong (bad credentials, network, ...) ->
          InputFetchError. Deliberately NOT FileNotFoundError: a broken
          credential must be loud, not look like a missing video.
        - The file appears in the cache atomically (temp name + rename), so
          a half-downloaded video is never mistaken for a cache hit.
        - A per-object file lock stops several gunicorn workers from each
          downloading the same object - S3 egress is billed per byte.
        """
        from boto3.s3.transfer import TransferConfig
        from botocore.exceptions import BotoCoreError, ClientError

        destination = self.cached_filename
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        lock_path = self._lock_path()
        os.makedirs(os.path.dirname(lock_path), exist_ok=True)

        with open(lock_path, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if os.path.exists(destination):
                    logger.debug(f"{self.source_uri} was fetched by another worker while waiting")
                    return

                tmp = f"{destination}.part-{os.getpid()}-{uuid.uuid4().hex[:8]}"
                logger.info(f"fetching {self.source_uri} -> {destination}")
                try:
                    self.client.download_file(
                        self.bucket, self.source_key, tmp,
                        Config=TransferConfig(
                            max_concurrency=int(self._opt('max_concurrency', '4') or 4),
                            multipart_threshold=16 * 1024 * 1024,
                            multipart_chunksize=16 * 1024 * 1024,
                        ),
                    )
                    os.replace(tmp, destination)
                except ClientError as e:
                    code = str(e.response.get('Error', {}).get('Code', ''))
                    if code in _MISSING_CODES:
                        logger.info(f"{self.source_uri} does not exist")
                        raise FileNotFoundError(self.source_uri) from e
                    if code in ('403', 'AccessDenied'):
                        # S3 also answers 403 (not 404) for a MISSING key when
                        # the credentials lack s3:ListBucket - so this can
                        # mean "denied" or "not there". Say both.
                        logger.error(f"access denied for {self.source_uri} (bad credentials, or a missing "
                                     f"key and no s3:ListBucket permission - see docs/s3-input.md)")
                    else:
                        logger.error(f"S3 error {code} fetching {self.source_uri}: {e}")
                    raise InputFetchError(f"S3 error {code} for {self.source_uri}") from e
                except BotoCoreError as e:
                    logger.error(f"S3 connection problem fetching {self.source_uri}: {e}")
                    raise InputFetchError(f"cannot reach S3 for {self.source_uri}") from e
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
