#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Where uploaded videos are written: the same place CasterPak reads them.

A storage 'key' is the library path CasterPak serves: '<username>/<dir>/<file>'.
Both backends refuse to overwrite - put() raises AlreadyExists - and both make
the object appear atomically, so CasterPak can never stream a half-uploaded file.
"""
import os
import shutil
import typing as t
import uuid
from configparser import ConfigParser

from werkzeug.utils import safe_join

import s3client
from library.settings import Settings


class StorageError(Exception):
    """The storage backend failed (disk full, S3 unreachable, ...)."""


class AlreadyExists(StorageError):
    pass


class Storage:
    kind = 'base'

    def put(self, key: str, stream: t.BinaryIO) -> int:
        """Write `stream` at `key`. Returns bytes written. Raises AlreadyExists."""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError

    def ensure_user_space(self, username: str) -> None:
        """Make the user's 'directory' exist, if the backend has such a thing."""


class LocalStorage(Storage):
    kind = 'filesystem'
    # Uploads are staged here, inside the library root so the final step is a
    # same-filesystem link/rename. The leading '.' keeps it out of every
    # CasterPak URL (usernames cannot start with '.').
    STAGING = '.incoming'

    def __init__(self, root: str):
        self.root = os.path.abspath(root)

    def _path(self, key: str) -> str:
        path = safe_join(self.root, key)
        if path is None:
            raise StorageError(f"unsafe storage key {key!r}")
        return path

    def ensure_user_space(self, username: str) -> None:
        os.makedirs(self._path(username), exist_ok=True)

    def exists(self, key: str) -> bool:
        return os.path.exists(self._path(key))

    def put(self, key: str, stream: t.BinaryIO) -> int:
        destination = self._path(key)
        staging_dir = os.path.join(self.root, self.STAGING)
        tmp = os.path.join(staging_dir, uuid.uuid4().hex)
        try:
            os.makedirs(staging_dir, exist_ok=True)
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            with open(tmp, 'wb') as out:
                shutil.copyfileobj(stream, out, length=1024 * 1024)
            size = os.path.getsize(tmp)
            try:
                # link() fails if the destination exists - an atomic
                # "create only if absent" that a plain rename is not.
                os.link(tmp, destination)
            except FileExistsError:
                raise AlreadyExists(key)
            except OSError:
                # filesystems without hard links (some network mounts)
                if os.path.exists(destination):
                    raise AlreadyExists(key)
                os.replace(tmp, destination)
            return size
        except AlreadyExists:
            raise
        except OSError as e:
            raise StorageError(f"could not write {key}: {e}") from e
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def delete(self, key: str) -> None:
        try:
            os.remove(self._path(key))
        except FileNotFoundError:
            pass


class S3Storage(Storage):
    kind = 's3'

    def __init__(self, client, bucket: str, prefix: str):
        self.client = client
        self.bucket = bucket
        self.prefix = prefix            # normalised: '' or 'x/y/'

    def _key(self, key: str) -> str:
        return self.prefix + key

    def exists(self, key: str) -> bool:
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as e:
            if str(e.response.get('Error', {}).get('Code')) in ('404', 'NoSuchKey', 'NotFound'):
                return False
            raise StorageError(f"S3 error checking {key}: {e}") from e
        except BotoCoreError as e:
            raise StorageError(f"cannot reach S3: {e}") from e

    def put(self, key: str, stream: t.BinaryIO) -> int:
        from boto3.s3.transfer import TransferConfig
        from botocore.exceptions import BotoCoreError, ClientError

        if self.exists(key):
            raise AlreadyExists(key)
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(0)
        try:
            # upload_fileobj switches to multipart on its own for big files;
            # the object only becomes visible when the upload completes.
            self.client.upload_fileobj(
                stream, self.bucket, self._key(key),
                Config=TransferConfig(multipart_threshold=16 * 1024 * 1024,
                                      multipart_chunksize=16 * 1024 * 1024))
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"S3 upload of {key} failed: {e}") from e
        return size

    def delete(self, key: str) -> None:
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self._key(key))
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"S3 delete of {key} failed: {e}") from e


def storage_from_config(settings: Settings, config: ConfigParser) -> Storage:
    if settings.input_type == 's3':
        bucket, prefix = s3client.bucket_and_prefix(config)
        return S3Storage(s3client.client_from_config(config), bucket, prefix)
    return LocalStorage(settings.library_root)
