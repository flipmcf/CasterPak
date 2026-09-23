#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Tests for the S3 input backend. No AWS involved: moto's mock_aws() answers
every S3 call in-process, and the one test that needs a real socket points
at a port nothing listens on. If a test here ever reaches real AWS, that is
a bug in the test - the fixture below plants fake credentials so it would be
rejected anyway.
"""
import configparser
import os
import threading
import time
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from pathsafety import InvalidPathError
from vodhls import ConfigurationError, InputFetchError
from vodhls import media_manifest_s3
from vodhls.media_manifest_s3 import MediaManager_s3

BUCKET = 'test-library'
BODY = b'not really an mp4, but bytes are bytes' * 1000


def make_config(cache_dir, **s3_overrides):
    cfg = configparser.ConfigParser()
    cfg['input'] = {'input_type': 's3', 'VideoCachePath': str(cache_dir)}
    cfg['s3'] = {
        'bucket': BUCKET, 'prefix': 'videos/', 'region': 'us-east-1',
        'endpoint_url': '', 'access_key_id': '', 'secret_access_key': '',
        'connect_timeout': '1', 'read_timeout': '2', 'max_attempts': '1',
    }
    cfg['s3'].update(s3_overrides)
    return cfg


@pytest.fixture
def aws(monkeypatch):
    """Fake credentials + an empty in-memory S3 with our bucket in it."""
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('AWS_EC2_METADATA_DISABLED', 'true')
    media_manifest_s3._client_for.cache_clear()
    with mock_aws():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        yield s3
    media_manifest_s3._client_for.cache_clear()


@pytest.fixture
def cache_dir(tmp_path):
    d = tmp_path / 'video_input'
    d.mkdir()
    return d


@pytest.fixture
def manager_cls(cache_dir, monkeypatch):
    """MediaManager_s3 with test config and no cache database."""
    monkeypatch.setattr(MediaManager_s3, 'config', make_config(cache_dir))
    monkeypatch.setattr(MediaManager_s3, 'db', mock.MagicMock())
    return MediaManager_s3


# --- URL -> key mapping ------------------------------------------------------

@pytest.mark.parametrize('prefix, expected', [
    ('videos/', 'videos/alice/clip.mp4'),
    ('videos', 'videos/alice/clip.mp4'),         # trailing slash is optional
    ('/videos//', 'videos/alice/clip.mp4'),      # stray slashes are tolerated
    ('archive/2026', 'archive/2026/alice/clip.mp4'),
    ('', 'alice/clip.mp4'),                      # bucket root
])
def test_url_path_maps_to_key_by_concatenation(manager_cls, cache_dir, monkeypatch, prefix, expected):
    monkeypatch.setattr(MediaManager_s3, 'config', make_config(cache_dir, prefix=prefix))
    m = manager_cls('alice/clip.mp4')
    assert m.source_key == expected
    assert m.source_uri == f's3://{BUCKET}/{expected}'


def test_key_never_starts_with_a_slash(manager_cls):
    assert not manager_cls('clip.mp4').source_key.startswith('/')


@pytest.mark.parametrize('bad', ['../etc/passwd', 'a/../b.mp4', '/abs.mp4', 'a//b.mp4', 'sp ace.mp4', 'a,b.mp4'])
def test_unsafe_paths_are_rejected_before_any_s3_call(manager_cls, bad):
    with pytest.raises(InvalidPathError):
        manager_cls(bad)


def test_missing_bucket_config_is_a_configuration_error(manager_cls, cache_dir, monkeypatch):
    monkeypatch.setattr(MediaManager_s3, 'config', make_config(cache_dir, bucket=''))
    with pytest.raises(ConfigurationError):
        manager_cls('clip.mp4')


def test_missing_s3_section_is_a_configuration_error(manager_cls, cache_dir, monkeypatch):
    cfg = make_config(cache_dir)
    cfg.remove_section('s3')
    monkeypatch.setattr(MediaManager_s3, 'config', cfg)
    with pytest.raises(ConfigurationError):
        manager_cls('clip.mp4')


# --- fetching ---------------------------------------------------------------

def test_fetch_downloads_into_the_input_cache(aws, manager_cls, cache_dir):
    aws.put_object(Bucket=BUCKET, Key='videos/alice/clip.mp4', Body=BODY)
    m = manager_cls('alice/clip.mp4')

    m.process_input()

    cached = cache_dir / 'alice' / 'clip.mp4'
    assert cached.read_bytes() == BODY
    assert m.input_file == str(cached)
    # the cache dir holds the file and the lock dir - no half-written leftovers
    assert not [p for p in cache_dir.rglob('*') if '.part-' in p.name]
    # ...and the cleaner is told about it, so the copy will age out.
    m.db.addrecord.assert_called_once_with(filename='alice/clip.mp4', timestamp=None)


def test_second_request_is_a_cache_hit_and_never_touches_s3(aws, manager_cls):
    aws.put_object(Bucket=BUCKET, Key='videos/clip.mp4', Body=BODY)
    manager_cls('clip.mp4').process_input()

    # Now the object vanishes - a cache hit must not care.
    aws.delete_object(Bucket=BUCKET, Key='videos/clip.mp4')
    with mock.patch.object(MediaManager_s3, 'fetch_and_cache') as fetch:
        manager_cls('clip.mp4').process_input()
    fetch.assert_not_called()


def test_missing_object_is_file_not_found(aws, manager_cls, cache_dir):
    with pytest.raises(FileNotFoundError):
        manager_cls('nope.mp4').process_input()
    assert not (cache_dir / 'nope.mp4').exists()
    assert not [p for p in cache_dir.rglob('*') if '.part-' in p.name]


def test_prefix_is_respected_objects_outside_it_are_invisible(aws, manager_cls):
    aws.put_object(Bucket=BUCKET, Key='other/clip.mp4', Body=BODY)   # not under videos/
    with pytest.raises(FileNotFoundError):
        manager_cls('clip.mp4').process_input()


def test_access_denied_is_loud_not_a_404(manager_cls):
    denied = ClientError({'Error': {'Code': '403', 'Message': 'Forbidden'}}, 'HeadObject')
    with mock.patch.object(MediaManager_s3, 'client', new_callable=mock.PropertyMock) as client:
        client.return_value.download_file.side_effect = denied
        with pytest.raises(InputFetchError):
            manager_cls('clip.mp4').process_input()


def test_unreachable_endpoint_is_input_fetch_error(manager_cls, cache_dir, monkeypatch, aws):
    # port 1: connection refused immediately, no network needed
    monkeypatch.setattr(MediaManager_s3, 'config',
                        make_config(cache_dir, endpoint_url='http://127.0.0.1:1'))
    with pytest.raises(InputFetchError):
        manager_cls('clip.mp4').process_input()


def test_failed_download_leaves_no_partial_file(manager_cls, cache_dir):
    def write_some_then_die(bucket, key, filename, **kwargs):
        with open(filename, 'wb') as f:
            f.write(b'half a video')
        raise ClientError({'Error': {'Code': '500', 'Message': 'boom'}}, 'GetObject')

    with mock.patch.object(MediaManager_s3, 'client', new_callable=mock.PropertyMock) as client:
        client.return_value.download_file.side_effect = write_some_then_die
        with pytest.raises(InputFetchError):
            manager_cls('clip.mp4').process_input()

    assert not [p for p in cache_dir.rglob('*') if p.is_file() and p.parent.name != '.locks']


def test_concurrent_requests_download_the_object_once(manager_cls, cache_dir):
    """Four gunicorn workers hitting a cold video: one S3 GET, not four."""
    calls = []

    def slow_download(bucket, key, filename, **kwargs):
        calls.append(key)
        time.sleep(0.3)
        with open(filename, 'wb') as f:
            f.write(BODY)

    errors = []

    def worker():
        try:
            manager_cls('clip.mp4').process_input()
        except Exception as e:      # pragma: no cover - surfaced below
            errors.append(e)

    with mock.patch.object(MediaManager_s3, 'client', new_callable=mock.PropertyMock) as client:
        client.return_value.download_file.side_effect = slow_download
        threads = [threading.Thread(target=worker) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]

    assert errors == []
    assert calls == ['videos/clip.mp4']
    assert (cache_dir / 'clip.mp4').read_bytes() == BODY


# --- client construction ----------------------------------------------------

def test_blank_credentials_fall_back_to_the_boto3_default_chain(aws, manager_cls):
    """No keys in config -> none passed to boto3, so it walks its own chain
    (env vars, shared credentials, EC2/ECS role)."""
    media_manifest_s3._client_for.cache_clear()
    with mock.patch('boto3.client') as boto_client:
        manager_cls('clip.mp4').client
    kwargs = boto_client.call_args.kwargs
    assert 'aws_access_key_id' not in kwargs
    assert 'aws_secret_access_key' not in kwargs


def test_configured_credentials_and_endpoint_are_used(aws, manager_cls, cache_dir, monkeypatch):
    monkeypatch.setattr(MediaManager_s3, 'config', make_config(
        cache_dir, endpoint_url='http://minio.internal:9000', access_key_id='AKIAEXAMPLE',
        secret_access_key='shhh', addressing_style='path'))
    client = manager_cls('clip.mp4').client
    assert client.meta.endpoint_url == 'http://minio.internal:9000'
    assert client._request_signer._credentials.access_key == 'AKIAEXAMPLE'


def test_client_is_shared_between_requests(aws, manager_cls):
    assert manager_cls('a.mp4').client is manager_cls('b.mp4').client


# --- wiring -----------------------------------------------------------------

@pytest.mark.parametrize('input_type', ['s3', 'S3'])
def test_factory_builds_an_s3_manager(manager_cls, cache_dir, input_type):
    from vodhls.factory import vodhls_media_playlist_factory
    cfg = make_config(cache_dir)
    cfg['input']['input_type'] = input_type
    with mock.patch('vodhls.factory.get_config', return_value=cfg):
        manager = vodhls_media_playlist_factory('alice/clip.mp4')
    assert isinstance(manager, MediaManager_s3)
