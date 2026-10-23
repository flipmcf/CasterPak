#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Many requests for a video that is not in the input cache yet must fetch it once (issue #65).
The others wait for the fetch, then find the file in the cache. A failed fetch leaves nothing
behind, and a reader never sees a partially written input file.
"""
import concurrent.futures
import configparser
import os
import shutil
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from vodhls.media_manifest_base import atomic_write, create_copy_lock
from vodhls.media_manifest_filesystem import MediaManager_filesystem
from vodhls.media_manifest_http import MediaManager_http

VIDEO = 'shows/2024/episode.mp4'
CONTENT = b'not really an mp4'


# --- create_copy_lock -------------------------------------------------------------------

def test_lock_admits_one_holder_at_a_time(tmp_path):
    lock_path = str(tmp_path / 'episode.mp4.lock')
    inside, overlaps = [], []
    guard = threading.Lock()

    def hold():
        with create_copy_lock(lock_path):
            with guard:
                inside.append(1)
                if len(inside) > 1:
                    overlaps.append(len(inside))
            time.sleep(0.005)
            with guard:
                inside.pop()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        list(pool.map(lambda _: hold(), range(200)))

    assert overlaps == []
    assert not os.path.exists(lock_path)


def test_lock_file_is_deleted_on_release_even_after_an_error(tmp_path):
    lock_path = str(tmp_path / 'episode.mp4.lock')
    with pytest.raises(RuntimeError):
        with create_copy_lock(lock_path):
            assert os.path.exists(lock_path)
            raise RuntimeError
    assert not os.path.exists(lock_path)


def test_a_stale_lock_file_left_by_a_crash_does_not_block(tmp_path):
    lock_path = tmp_path / 'episode.mp4.lock'
    lock_path.write_bytes(b'')          # nobody holds it, as after a worker was killed

    with create_copy_lock(str(lock_path)):
        pass

    assert not lock_path.exists()


# --- atomic_write ---------------------------------------------------------------------------

def test_atomic_write_replaces_the_destination_on_success(tmp_path):
    destination = tmp_path / 'episode.mp4'
    with atomic_write(str(destination)) as tmp:
        with open(tmp, 'wb') as f:
            f.write(CONTENT)
        assert not destination.exists()     # nothing visible until the body is done

    assert destination.read_bytes() == CONTENT
    assert os.listdir(tmp_path) == ['episode.mp4']


def test_atomic_write_leaves_nothing_when_the_body_fails(tmp_path):
    destination = tmp_path / 'episode.mp4'
    with pytest.raises(RuntimeError):
        with atomic_write(str(destination)) as tmp:
            with open(tmp, 'wb') as f:
                f.write(CONTENT[:4])
            raise RuntimeError

    assert os.listdir(tmp_path) == []


# --- input types ----------------------------------------------------------------------------

@pytest.fixture
def dirs(tmp_path):
    library, cache = tmp_path / 'library', tmp_path / 'cache'
    (library / 'shows' / '2024').mkdir(parents=True)
    (library / VIDEO).write_bytes(CONTENT)
    cache.mkdir()

    cfg = configparser.ConfigParser()
    cfg.read_dict({
        'input': {'videoCachePath': str(cache)},
        'filesystem': {'videoParentPath': str(library), 'cache_input': 'True'},
        'http': {'url': 'http://library.example.com/', 'connect_timeout': '1', 'transfer_timeout': '1'},
    })
    return {'library': library, 'cache': cache, 'cfg': cfg}


def slow_filesystem(dirs, fetches):
    """MediaManager_filesystem whose copy is slow and counted."""
    real_copy = shutil.copy

    def copy(src, dst):
        fetches.append(src)
        time.sleep(0.2)
        return real_copy(src, dst)

    return [patch.object(MediaManager_filesystem, 'config', dirs['cfg']),
            patch('vodhls.media_manifest_filesystem.shutil.copy', side_effect=copy)], MediaManager_filesystem


def slow_http(dirs, fetches, status=200):
    """MediaManager_http whose download is slow and counted."""
    def get(url, *args, **kwargs):
        fetches.append(url)
        response = MagicMock(status_code=status)
        response.__enter__.return_value = response

        def chunks(chunk_size):
            time.sleep(0.2)
            yield CONTENT

        response.iter_content.side_effect = chunks
        return response

    return [patch.object(MediaManager_http, 'config', dirs['cfg']),
            patch('vodhls.media_manifest_http.requests.get', side_effect=get)], MediaManager_http


INPUT_TYPES = {'filesystem': slow_filesystem, 'http': slow_http}


def run_with(patches, fn):
    for p in patches:
        p.start()
    try:
        return fn()
    finally:
        for p in reversed(patches):
            p.stop()


@pytest.mark.parametrize('input_type', INPUT_TYPES)
def test_concurrent_requests_fetch_the_input_file_once(dirs, input_type):
    fetches = []
    patches, manager_cls = INPUT_TYPES[input_type](dirs, fetches)
    patches.append(patch.object(manager_cls, 'db', MagicMock()))

    def request():
        manager_cls(VIDEO).process_input()

    def stampede():
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for future in [pool.submit(request) for _ in range(8)]:
                future.result()

    run_with(patches, stampede)

    assert len(fetches) == 1
    assert (dirs['cache'] / VIDEO).read_bytes() == CONTENT
    # no lock file and no temporary file are left in the cache
    assert os.listdir(dirs['cache'] / 'shows' / '2024') == ['episode.mp4']


def test_a_failed_http_fetch_leaves_nothing_in_the_cache(dirs):
    patches, manager_cls = slow_http(dirs, [], status=404)
    patches.append(patch.object(manager_cls, 'db', MagicMock()))

    with pytest.raises(FileNotFoundError):
        run_with(patches, lambda: manager_cls(VIDEO).process_input())

    assert os.listdir(dirs['cache'] / 'shows' / '2024') == []


def test_a_missing_filesystem_source_leaves_nothing_in_the_cache(dirs):
    (dirs['library'] / VIDEO).unlink()
    patches = [patch.object(MediaManager_filesystem, 'config', dirs['cfg']),
               patch.object(MediaManager_filesystem, 'db', MagicMock())]

    with pytest.raises(FileNotFoundError):
        run_with(patches, lambda: MediaManager_filesystem(VIDEO).process_input())

    assert os.listdir(dirs['cache'] / 'shows' / '2024') == []


@pytest.mark.parametrize('manager_cls', [MediaManager_filesystem, MediaManager_http])
def test_every_input_type_locks_its_fetch(manager_cls):
    # functools.wraps in locked_fetch sets __wrapped__
    assert hasattr(manager_cls.fetch_and_cache, '__wrapped__')
