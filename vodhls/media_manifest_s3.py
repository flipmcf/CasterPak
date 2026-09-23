#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import fcntl
import functools
import hashlib
import logging
import os
import typing as t
import uuid

from vodhls import ConfigurationError, InputFetchError
from vodhls.media_manifest_base import MediaManager_Base
from pathsafety import validate_filename

logger = logging.getLogger('vodhls')

# S3 answers a missing key with one of these, depending on the call and on
# whether the caller may ListBucket (see fetch_and_cache).
_MISSING_CODES = {'404', 'NoSuchKey', 'NotFound'}


@functools.lru_cache(maxsize=4)
def _client_for(endpoint_url, region, access_key_id, secret_access_key,
                addressing_style, connect_timeout, read_timeout, max_attempts):
    """One boto3 client per distinct configuration. boto3 clients are
    thread-safe, and creating one is expensive (it loads the service model),
    so it is shared by every request in the worker. Arguments are all
    hashable strings/numbers so this can be an lru_cache."""
    import boto3
    from botocore.config import Config

    kwargs = {}
    if endpoint_url:
        kwargs['endpoint_url'] = endpoint_url
    if region:
        kwargs['region_name'] = region
    # Blank keys mean "use boto3's default credential chain" - env vars,
    # shared credentials, or (on EC2/ECS) the instance/task role. Preferred
    # in production: no secret ever lands in config.ini.
    if access_key_id and secret_access_key:
        kwargs['aws_access_key_id'] = access_key_id
        kwargs['aws_secret_access_key'] = secret_access_key

    return boto3.client(
        's3',
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': addressing_style},
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            retries={'max_attempts': max_attempts, 'mode': 'standard'},
        ),
        **kwargs,
    )


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
        if not self.config.has_section('s3'):
            raise ConfigurationError("input_type is s3 but config.ini has no [s3] section")
        return self.config.get('s3', option, fallback=fallback).strip()

    @property
    def bucket(self) -> str:
        bucket = self._opt('bucket')
        if not bucket:
            raise ConfigurationError("[s3] bucket is not configured")
        return bucket

    @property
    def prefix(self) -> str:
        """The configured key prefix, normalised: no leading '/', and exactly
        one trailing '/' unless it is empty (bucket root)."""
        prefix = self._opt('prefix').strip('/')
        return prefix + '/' if prefix else ''

    @property
    def source_key(self) -> str:
        return self.prefix + self.filename

    @property
    def source_uri(self) -> str:
        return f"s3://{self.bucket}/{self.source_key}"

    @property
    def client(self):
        return _client_for(
            self._opt('endpoint_url') or None,
            self._opt('region') or None,
            self._opt('access_key_id'),
            self._opt('secret_access_key'),
            self._opt('addressing_style', 'auto') or 'auto',
            float(self._opt('connect_timeout', '5') or 5),
            float(self._opt('read_timeout', '60') or 60),
            int(self._opt('max_attempts', '3') or 3),
        )

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
