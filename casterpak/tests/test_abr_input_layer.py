#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
/i/abr/ gets its source video from the input layer, so it works with every input type.

These tests run the real input layer (MediaManager_Base.process_input -> fetch_and_cache -> input_file)
and the real EncodingManager. The only stand-ins are:
  - RemoteInput, a non-filesystem input type whose "remote" is a directory the test fills; and
  - the places that would start ffmpeg (the encode queue and the JIT stream).
The app has NO [filesystem] section at all: nothing on the /i/abr/ path may read one.
"""
import configparser
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from casterpak.routes import bp
from vodhls.media_manifest_base import MediaManager_Base


@pytest.fixture
def stack(tmp_path):
    remote = tmp_path / 'remote'
    cache = tmp_path / 'cache'
    segments = tmp_path / 'segments'
    for d in (remote, cache, segments):
        d.mkdir()

    cfg = configparser.ConfigParser()
    cfg.read_dict({
        'input': {'input_type': 'remote', 'videoCachePath': str(cache)},
        'output': {'segmentParentPath': str(segments), 'childManifestFilename': 'index_0_av.m3u8',
                   'serverName': ''},
    })

    class RemoteInput(MediaManager_Base):
        """A non-filesystem input type: the source lives in `remote` and is copied into the input cache."""
        def fetch_and_cache(self):
            source = remote / self.filename
            if not source.exists():
                raise FileNotFoundError(self.filename)
            os.makedirs(os.path.dirname(self.cached_filename), exist_ok=True)
            shutil.copy(source, self.cached_filename)

    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['input'] = cfg['input']
    app.config['output'] = cfg['output']          # note: no app.config['filesystem']

    queued = []
    with patch.object(RemoteInput, 'config', cfg), \
         patch.object(RemoteInput, 'db', MagicMock()), \
         patch('casterpak.routes.vodhls_media_playlist_factory', side_effect=lambda name: RemoteInput(name)), \
         patch('encoding.encodingmanager.get_config', return_value=cfg), \
         patch('encoding.encodingmanager.EncodingManager.queue_encoding_job',
               side_effect=lambda command: queued.append(command)), \
         patch('encoding.encodingmanager.EncodingManager.in_progress', return_value=False), \
         patch('casterpak.routes.jit_manager_factory') as jit_factory:
        jit = MagicMock()
        jit.first_segment_exists.return_value = False
        jit.get_m3u8_index_url.return_value = '/i/JIT_shows/clip.mp4/index_0_av.m3u8'
        jit_factory.return_value = jit
        with app.app_context():
            yield {'client': app.test_client(), 'remote': remote, 'cache': cache,
                   'queued': queued, 'jit_factory': jit_factory}


def test_abr_works_with_a_non_filesystem_input(stack):
    (stack['remote'] / 'shows').mkdir()
    (stack['remote'] / 'shows' / 'clip.mp4').write_bytes(b'not really an mp4')
    cached_source = stack['cache'] / 'shows' / 'clip.mp4'

    response = stack['client'].get('/i/abr/shows/clip.mp4/master.m3u8')

    assert response.status_code == 200
    assert b'#EXTM3U' in response.data

    # the input layer fetched the source into the input cache...
    assert cached_source.read_bytes() == b'not really an mp4'

    # ...the background encode reads that local file and writes under the library-path-keyed directory...
    (command,) = stack['queued']
    assert command[command.index('-i') + 1] == str(cached_source)
    transcodes = str(stack['cache'] / 'shows' / 'clip.mp4.transcodes')
    outputs = [arg for arg in command if arg.endswith('.mp4') and arg != str(cached_source)]
    assert outputs and all(o.startswith(transcodes + '/clip_') for o in outputs)

    # ...and so does the JIT stream.
    assert stack['jit_factory'].call_args.kwargs['input_filepath'] == str(cached_source)


def test_abr_missing_source_is_404_and_encodes_nothing(stack):
    response = stack['client'].get('/i/abr/shows/missing.mp4/master.m3u8')

    assert response.status_code == 404
    assert stack['queued'] == []
    stack['jit_factory'].assert_not_called()
