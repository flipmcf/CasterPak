#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""Storage backends: the filesystem library and the S3 library. No AWS
involved - moto answers S3 in-process (see vodhls/tests/test_media_manifest_s3.py)."""
import io
import os
import threading

import boto3
import pytest
from moto import mock_aws

import s3client
from library import create_app
from library.storage import AlreadyExists, LocalStorage, S3Storage, StorageError
from library.tests.conftest import bearer, fake_mp4, login, make_config, register, upload

BUCKET = 'library-test'


# --- LocalStorage ---------------------------------------------------------------

def test_local_put_creates_directories_and_reports_size(tmp_path):
    s = LocalStorage(str(tmp_path))
    assert s.put('alice/a/b/c.mp4', io.BytesIO(b'12345')) == 5
    assert (tmp_path / 'alice' / 'a' / 'b' / 'c.mp4').read_bytes() == b'12345'
    assert s.exists('alice/a/b/c.mp4') and not s.exists('alice/nope.mp4')


def test_local_put_never_overwrites(tmp_path):
    s = LocalStorage(str(tmp_path))
    s.put('alice/a.mp4', io.BytesIO(b'first'))
    with pytest.raises(AlreadyExists):
        s.put('alice/a.mp4', io.BytesIO(b'second'))
    assert (tmp_path / 'alice' / 'a.mp4').read_bytes() == b'first'
    assert list((tmp_path / '.incoming').iterdir()) == []


@pytest.mark.parametrize('key', ['../evil.mp4', 'alice/../../evil.mp4', '/etc/evil.mp4'])
def test_local_refuses_keys_that_escape_the_root(tmp_path, key):
    with pytest.raises(StorageError):
        LocalStorage(str(tmp_path / 'root')).put(key, io.BytesIO(b'x'))
    assert not (tmp_path / 'evil.mp4').exists()


def test_local_racing_uploads_of_the_same_key_produce_exactly_one_winner(tmp_path):
    s = LocalStorage(str(tmp_path))
    results = []

    def go(n):
        try:
            s.put('alice/race.mp4', io.BytesIO(b'writer-%d' % n))
            results.append('ok')
        except AlreadyExists:
            results.append('conflict')

    threads = [threading.Thread(target=go, args=(n,)) for n in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ['conflict'] * 7 + ['ok']


def test_local_falls_back_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    def no_links(*a, **k):
        raise OSError(1, 'Operation not permitted')       # e.g. some network mounts
    monkeypatch.setattr(os, 'link', no_links)
    s = LocalStorage(str(tmp_path))
    s.put('alice/a.mp4', io.BytesIO(b'data'))
    assert (tmp_path / 'alice' / 'a.mp4').read_bytes() == b'data'
    with pytest.raises(AlreadyExists):
        s.put('alice/a.mp4', io.BytesIO(b'again'))


def test_upload_reports_503_when_the_store_is_broken(client, alice, library_root, monkeypatch):
    def broken(self, key, stream):
        raise StorageError('disk on fire')
    monkeypatch.setattr(LocalStorage, 'put', broken)
    r = upload(client, alice[0], filename='a.mp4')
    assert r.status_code == 503 and r.get_json()['error']['code'] == 'storage_error'
    assert 'disk on fire' not in r.get_data(as_text=True)        # internals aren't leaked
    assert client.get('/api/videos', headers=alice[0]).get_json()['total'] == 0


def test_file_is_removed_if_the_index_write_fails(client, alice, library_root, monkeypatch):
    from library.models import db
    original_commit = db.session.commit

    def boom():
        raise RuntimeError('db died')
    upload_ok = upload(client, alice[0], filename='first.mp4')      # sanity: normal path works
    assert upload_ok.status_code == 201

    monkeypatch.setattr(db.session, 'commit', boom)
    r = upload(client, alice[0], filename='second.mp4')
    monkeypatch.setattr(db.session, 'commit', original_commit)
    assert r.status_code == 500
    assert not (library_root / 'alice' / 'second.mp4').exists()     # no orphan left in the library


# --- S3 -----------------------------------------------------------------------------------

@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv('AWS_ACCESS_KEY_ID', 'testing')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'testing')
    monkeypatch.setenv('AWS_DEFAULT_REGION', 'us-east-1')
    monkeypatch.setenv('AWS_EC2_METADATA_DISABLED', 'true')
    s3client._client_for.cache_clear()
    with mock_aws():
        client = boto3.client('s3', region_name='us-east-1')
        client.create_bucket(Bucket=BUCKET)
        yield client
    s3client._client_for.cache_clear()


def test_s3_put_writes_under_the_prefix_and_never_overwrites(s3):
    store = S3Storage(s3, BUCKET, 'videos/')
    assert store.put('alice/a.mp4', io.BytesIO(b'hello')) == 5
    assert s3.get_object(Bucket=BUCKET, Key='videos/alice/a.mp4')['Body'].read() == b'hello'
    assert store.exists('alice/a.mp4')
    with pytest.raises(AlreadyExists):
        store.put('alice/a.mp4', io.BytesIO(b'other'))
    assert s3.get_object(Bucket=BUCKET, Key='videos/alice/a.mp4')['Body'].read() == b'hello'


def test_s3_unreachable_is_a_storage_error():
    s3client._client_for.cache_clear()
    import botocore.config
    dead = boto3.client('s3', endpoint_url='http://127.0.0.1:1', region_name='us-east-1',
                        aws_access_key_id='x', aws_secret_access_key='y',
                        config=botocore.config.Config(retries={'max_attempts': 1}, connect_timeout=1))
    with pytest.raises(StorageError):
        S3Storage(dead, BUCKET, '').put('alice/a.mp4', io.BytesIO(b'x'))


def s3_app(tmp_path, **library):
    cfg = make_config(tmp_path, **library)
    cfg['input']['input_type'] = 's3'
    cfg['s3'] = {'bucket': BUCKET, 'prefix': 'videos/', 'region': 'us-east-1', 'max_attempts': '1'}
    return create_app(cfg)


def test_whole_flow_against_an_s3_library(tmp_path, s3):
    """Register -> upload -> list against S3. The object lands at
    <prefix>/<user>/<path>: exactly the key CasterPak's s3 input derives from
    the URL /i/<user>/<path>/..., so it is streamable immediately."""
    client = s3_app(tmp_path).test_client()
    assert client.get('/api/health').get_json()['storage'] == 's3'
    register(client)
    headers = bearer(login(client).get_json()['access_token'])

    r = upload(client, headers, fake_mp4(3000), 'clip.mp4', path='trips')
    assert r.status_code == 201
    keys = [o['Key'] for o in s3.list_objects_v2(Bucket=BUCKET)['Contents']]
    assert keys == ['videos/alice/trips/clip.mp4']

    body = r.get_json()
    assert 'abr' not in body['urls']                    # CasterPak can't auto-encode from S3 yet
    assert body['urls']['hls'] == body['urls']['single']
    assert body['urls']['single'] == 'https://video.example.test/i/alice/trips/clip.mp4/master.m3u8'

    assert upload(client, headers, filename='clip.mp4', path='trips').status_code == 409
    assert client.get('/api/videos', headers=headers).get_json()['total'] == 1


def test_s3_outage_during_upload_is_a_503_and_leaves_no_record(tmp_path, s3, monkeypatch):
    app = s3_app(tmp_path)
    client = app.test_client()
    register(client)
    headers = bearer(login(client).get_json()['access_token'])

    def down(self, key, stream):
        raise StorageError('S3 is down')
    monkeypatch.setattr(S3Storage, 'put', down)
    assert upload(client, headers, filename='a.mp4').status_code == 503
    assert client.get('/api/videos', headers=headers).get_json()['total'] == 0
