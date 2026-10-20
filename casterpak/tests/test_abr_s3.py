#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
/i/abr/ with input_type = s3. The real S3 input manager runs against moto (an in-process fake S3),
and the real input layer and EncodingManager do the rest; only the places that would start ffmpeg
(the encode queue and the JIT stream) are stand-ins. The app has no [filesystem] section.
"""
import configparser
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from flask import Flask
from moto import mock_aws

import s3client
from casterpak.routes import bp
from vodhls.media_manifest_s3 import MediaManager_s3

BUCKET = 'test-library'
BODY = b'not really an mp4, but bytes are bytes' * 100


@pytest.fixture
def stack(tmp_path, monkeypatch):
    for name, value in (('AWS_ACCESS_KEY_ID', 'testing'), ('AWS_SECRET_ACCESS_KEY', 'testing'),
                        ('AWS_DEFAULT_REGION', 'us-east-1'), ('AWS_EC2_METADATA_DISABLED', 'true')):
        monkeypatch.setenv(name, value)
    s3client._client_for.cache_clear()

    cache, segments = tmp_path / 'cache', tmp_path / 'segments'
    cache.mkdir()
    segments.mkdir()
    cfg = configparser.ConfigParser()
    cfg.read_dict({
        'input': {'input_type': 's3', 'VideoCachePath': str(cache)},
        's3': {'bucket': BUCKET, 'prefix': 'videos/', 'region': 'us-east-1', 'endpoint_url': '',
               'access_key_id': '', 'secret_access_key': '', 'connect_timeout': '1',
               'read_timeout': '2', 'max_attempts': '1'},
        'output': {'segmentParentPath': str(segments), 'childManifestFilename': 'index_0_av.m3u8',
                   'serverName': ''},
    })

    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['input'] = cfg['input']
    app.config['output'] = cfg['output']

    queued = []
    with mock_aws():
        s3 = boto3.client('s3', region_name='us-east-1')
        s3.create_bucket(Bucket=BUCKET)
        with mock.patch.object(MediaManager_s3, 'config', cfg), \
             mock.patch.object(MediaManager_s3, 'db', mock.MagicMock()), \
             mock.patch('casterpak.routes.vodhls_media_playlist_factory',
                        side_effect=lambda name: MediaManager_s3(name)), \
             mock.patch('encoding.encodingmanager.get_config', return_value=cfg), \
             mock.patch('encoding.encodingmanager.EncodingManager.queue_encoding_job',
                        side_effect=lambda command: queued.append(command)), \
             mock.patch('encoding.encodingmanager.EncodingManager.in_progress', return_value=False), \
             mock.patch('casterpak.routes.jit_manager_factory') as jit_factory:
            jit = mock.MagicMock()
            jit.first_segment_exists.return_value = False
            jit.get_m3u8_index_url.return_value = '/i/JIT_shows/clip.mp4/index_0_av.m3u8'
            jit_factory.return_value = jit
            with app.app_context():
                yield {'client': app.test_client(), 's3': s3, 'cache': cache,
                       'queued': queued, 'jit_factory': jit_factory}
    s3client._client_for.cache_clear()


def test_abr_works_with_an_s3_library(stack):
    stack['s3'].put_object(Bucket=BUCKET, Key='videos/shows/clip.mp4', Body=BODY)   # prefix + URL path
    cached_source = stack['cache'] / 'shows' / 'clip.mp4'

    response = stack['client'].get('/i/abr/shows/clip.mp4/master.m3u8')

    assert response.status_code == 200
    assert b'#EXTM3U' in response.data

    # the input layer downloaded the object into the input cache...
    assert cached_source.read_bytes() == BODY

    # ...the background encode reads that local file and writes under the library-path-keyed directory...
    (command,) = stack['queued']
    assert command[command.index('-i') + 1] == str(cached_source)
    transcodes = str(stack['cache'] / 'shows' / 'clip.mp4.transcodes')
    outputs = [arg for arg in command if arg.endswith('.mp4') and arg != str(cached_source)]
    assert outputs and all(o.startswith(transcodes + '/clip_') for o in outputs)

    # ...and so does the JIT stream.
    assert stack['jit_factory'].call_args.kwargs['input_filepath'] == str(cached_source)


def test_abr_s3_object_downloaded_once_for_repeated_requests(stack):
    stack['s3'].put_object(Bucket=BUCKET, Key='videos/shows/clip.mp4', Body=BODY)

    with mock.patch.object(MediaManager_s3, 'fetch_and_cache', autospec=True,
                           side_effect=MediaManager_s3.fetch_and_cache) as fetch:
        for _ in range(3):
            assert stack['client'].get('/i/abr/shows/clip.mp4/master.m3u8').status_code == 200

    assert fetch.call_count == 1          # fetched once; later requests use the cached copy


def test_abr_s3_missing_object_is_404_and_encodes_nothing(stack):
    response = stack['client'].get('/i/abr/shows/missing.mp4/master.m3u8')

    assert response.status_code == 404
    assert stack['queued'] == []
    stack['jit_factory'].assert_not_called()


def test_abr_s3_failure_is_500_and_does_not_leak_the_bucket(stack):
    denied = ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'denied'}}, 'GetObject')
    with mock.patch.object(MediaManager_s3, 'client', new_callable=mock.PropertyMock) as client:
        client.return_value.download_file.side_effect = denied
        response = stack['client'].get('/i/abr/shows/clip.mp4/master.m3u8')

    assert response.status_code == 500
    assert BUCKET.encode() not in response.data and b's3://' not in response.data
    assert stack['queued'] == []
    stack['jit_factory'].assert_not_called()
