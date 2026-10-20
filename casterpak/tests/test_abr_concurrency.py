#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
/i/abr/ for two DIFFERENT videos at the same time must not serialize or block each other, even
when the files share a basename (videos/2026/10/2/video.mp4 and videos/2026/10/5/video.mp4).
Hits for the SAME video must still collapse into one encode.

The encode queue's lock is the video's full library path, and the JIT lock is a per-video
directory (JIT_<name> next to the video's own segment directory). This runs the real
EncodingManager, queue, JitManager and filesystem input; only ffmpeg itself is faked.
"""
import concurrent.futures
import configparser
import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from casterpak.routes import bp
from encoding import encoding_process_manager as epm
from vodhls.media_manifest_filesystem import MediaManager_filesystem

URL_A = '/i/abr/videos/2026/10/2/video.mp4/master.m3u8'
URL_B = '/i/abr/videos/2026/10/5/video.mp4/master.m3u8'


@pytest.fixture
def stack(tmp_path):
    library, cache, segments = tmp_path / 'library', tmp_path / 'cache', tmp_path / 'segments'
    for day in ('2', '5'):
        (library / 'videos' / '2026' / '10' / day).mkdir(parents=True)
        (library / 'videos' / '2026' / '10' / day / 'video.mp4').write_bytes(b'not really an mp4 ' + day.encode())
    cache.mkdir()
    segments.mkdir()

    cfg = configparser.ConfigParser()
    cfg.read_dict({
        'input': {'input_type': 'filesystem', 'videoCachePath': str(cache)},
        'filesystem': {'videoParentPath': str(library), 'cache_input': 'False'},
        'output': {'segmentParentPath': str(segments), 'childManifestFilename': 'index_0_av.m3u8',
                   'serverName': ''},
    })

    queue_db = str(tmp_path / 'queue.sqlite')
    epm.initialize_encoding_db(queue_db)

    ffmpeg_started = []                 # the "-i" source of every ffmpeg the JIT stream starts

    def fake_popen(cmd, **kwargs):
        ffmpeg_started.append(cmd[cmd.index('-i') + 1])
        # a real ffmpeg writes its first segment; the request waits for it
        first_segment = cmd[cmd.index('-hls_segment_filename') + 1] % 0
        with open(first_segment, 'wb') as f:
            f.write(b'ts')
        return MagicMock(poll=lambda: None)

    app = Flask(__name__)
    app.register_blueprint(bp)
    app.config['input'] = cfg['input']
    app.config['output'] = cfg['output']

    with patch.object(MediaManager_filesystem, 'config', cfg), \
         patch.object(MediaManager_filesystem, 'db', MagicMock()), \
         patch('casterpak.routes.vodhls_media_playlist_factory',
               side_effect=lambda name: MediaManager_filesystem(name)), \
         patch('encoding.encodingmanager.get_config', return_value=cfg), \
         patch('encoding.encodingmanager.EncodingManager.get_ffmpeg_command', return_value=['ffmpeg']), \
         patch.object(epm, '_queue', epm.SqliteEncodingQueue(queue_db)), \
         patch('jit.jit_manager.subprocess.Popen', side_effect=fake_popen):
        yield {'app': app, 'segments': segments, 'library': library,
               'queue_rows': lambda: sorted(r[0] for r in sqlite3.connect(queue_db).execute(
                   'SELECT lock_name FROM encodingqueue')),
               'ffmpeg_started': ffmpeg_started}


def hit(app, url):
    return app.test_client().get(url)


def test_two_videos_with_the_same_basename_do_not_lock_each_other(stack):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda url: hit(stack['app'], url), [URL_A, URL_B]))

    assert [r.status_code for r in responses] == [200, 200]

    # each video got its own encode-queue entry, keyed by its full library path
    assert stack['queue_rows']() == ['videos/2026/10/2/video.mp4', 'videos/2026/10/5/video.mp4']

    # each video got its own JIT stream, from its own source, in its own directory
    assert sorted(stack['ffmpeg_started']) == sorted(
        str(stack['library'] / 'videos' / '2026' / '10' / day / 'video.mp4') for day in ('2', '5'))
    for day, response in zip(('2', '5'), responses):
        jit_dir = stack['segments'] / 'videos' / '2026' / '10' / day / 'JIT_video.mp4'
        assert (jit_dir / 'segment-0.ts').exists()
        assert f'/i/videos/2026/10/{day}/JIT_video.mp4/index_0_av.m3u8' in response.text


def test_a_stampede_on_two_videos_still_runs_one_encode_each(stack):
    urls = [URL_A, URL_B] * 4                                  # 8 near-simultaneous requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda url: hit(stack['app'], url), urls))

    assert all(r.status_code == 200 for r in responses), [r.status_code for r in responses]
    assert stack['queue_rows']() == ['videos/2026/10/2/video.mp4', 'videos/2026/10/5/video.mp4']
    assert len(stack['ffmpeg_started']) == 2
