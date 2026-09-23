#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import io

import pytest

from library import create_app
from library.tests.conftest import ASSET, bearer, fake_mp4, login, make_config, register, upload

WEBM = b'\x1a\x45\xdf\xa3' + b'\x00' * 512


def error_code(response):
    return response.get_json()['error']['code']


# --- the happy path ------------------------------------------------------------

def test_upload_stores_the_file_in_the_users_directory(client, alice, library_root):
    headers, _ = alice
    content = fake_mp4(5000)
    r = upload(client, headers, content, 'holiday.mp4')

    assert r.status_code == 201
    assert (library_root / 'alice' / 'holiday.mp4').read_bytes() == content
    body = r.get_json()
    assert body['path'] == 'alice/holiday.mp4'
    assert body['name'] == 'holiday.mp4'
    assert body['directory'] == ''
    assert body['size'] == len(content)
    assert body['created_at'].endswith('Z')
    assert r.headers['Location'] == '/api/videos/alice/holiday.mp4'


def test_response_carries_the_urls_needed_to_embed_the_video(client, alice):
    body = upload(client, alice[0], filename='holiday.mp4').get_json()
    assert body['urls'] == {
        'single': 'https://video.example.test/i/alice/holiday.mp4/master.m3u8',
        'abr': 'https://video.example.test/i/abr/alice/holiday.mp4/master.m3u8',
        'hls': 'https://video.example.test/i/abr/alice/holiday.mp4/master.m3u8',
    }
    assert 'https://video.example.test/i/abr/alice/holiday.mp4/master.m3u8' in body['embed_html']
    assert body['embed_html'].count('<video') == 1
    assert 'hls.js' in body['embed_html']


def test_upload_into_a_nested_directory(client, alice, library_root):
    r = upload(client, alice[0], filename='clip.mp4', path='/trips/2026/')
    assert r.status_code == 201
    assert (library_root / 'alice' / 'trips' / '2026' / 'clip.mp4').exists()
    body = r.get_json()
    assert body['path'] == 'alice/trips/2026/clip.mp4'
    assert body['directory'] == 'trips/2026'


def test_filename_field_overrides_the_uploaded_name(client, alice, library_root):
    r = upload(client, alice[0], filename='IMG 0001 (final).mp4', form={'filename': 'holiday.mp4'})
    assert r.status_code == 201
    assert (library_root / 'alice' / 'holiday.mp4').exists()


def test_a_real_mp4_is_accepted(client, alice, library_root):
    if not ASSET.exists():
        pytest.skip('tests/assets/test-video.mp4 not present')
    r = upload(client, alice[0], ASSET.read_bytes(), 'real.mp4')
    assert r.status_code == 201
    assert (library_root / 'alice' / 'real.mp4').stat().st_size == ASSET.stat().st_size


def test_webm_is_accepted_by_its_own_signature(client, alice):
    assert upload(client, alice[0], WEBM, 'clip.webm').status_code == 201


def test_no_staging_files_are_left_behind(client, alice, library_root):
    upload(client, alice[0], filename='ok.mp4')
    upload(client, alice[0], filename='ok.mp4')          # duplicate -> 409
    upload(client, alice[0], b'nope', 'bad.mp4')          # rejected
    assert list((library_root / '.incoming').glob('*')) == []


# --- authorization ---------------------------------------------------------------

def test_upload_requires_an_account(client):
    r = client.post('/api/upload', data={'file': (io.BytesIO(fake_mp4()), 'a.mp4')},
                    content_type='multipart/form-data')
    assert r.status_code == 401


def test_users_only_ever_write_to_their_own_directory(client, alice, bob, library_root):
    # There is no field that can address another user's directory: 'path' is
    # always relative to your own, and '..' is rejected.
    r = upload(client, alice[0], filename='x.mp4', path='../bob')
    assert r.status_code == 422 and error_code(r) == 'invalid_path'
    r = upload(client, alice[0], filename='x.mp4', path='/bob/')       # -> alice/bob/x.mp4
    assert r.status_code == 201 and r.get_json()['path'] == 'alice/bob/x.mp4'
    assert not (library_root / 'bob' / 'x.mp4').exists()


# --- validation ---------------------------------------------------------------------

@pytest.mark.parametrize('name', ['my video.mp4', 'a,b.mp4', '-flag.mp4', '..', 'a/b.mp4', 'é.mp4', '.mp4/'])
def test_invalid_filenames_are_rejected_not_rewritten(client, alice, library_root, name):
    r = upload(client, alice[0], filename=name)
    assert r.status_code in (415, 422)
    assert not any(p.is_file() for p in (library_root / 'alice').rglob('*'))


def test_rejection_explains_the_rules(client, alice):
    r = upload(client, alice[0], filename='my video.mp4')
    assert r.status_code == 422 and error_code(r) == 'invalid_filename'
    assert 'no spaces' in r.get_json()['error']['message']


@pytest.mark.parametrize('directory', ['a//b', 'a/../b', 'sp ace', 'a,b', '//', 'a/./b'])
def test_invalid_directories_are_rejected(client, alice, directory):
    r = upload(client, alice[0], filename='ok.mp4', path=directory)
    assert r.status_code == 422 and error_code(r) == 'invalid_path'


@pytest.mark.parametrize('name', ['notes.txt', 'run.exe', 'page.html', 'noextension'])
def test_unsupported_extensions(client, alice, name):
    r = upload(client, alice[0], filename=name)
    assert r.status_code == 415 and error_code(r) == 'unsupported_type'


def test_content_must_match_the_extension(client, alice):
    r = upload(client, alice[0], b'<html><script>alert(1)</script></html>', 'evil.mp4')
    assert r.status_code == 415 and error_code(r) == 'not_a_video'
    r = upload(client, alice[0], fake_mp4(), 'really-an-mp4.webm')      # mp4 bytes, webm name
    assert r.status_code == 415 and error_code(r) == 'not_a_video'


def test_empty_file(client, alice):
    r = upload(client, alice[0], b'', 'empty.mp4')
    assert r.status_code == 400 and error_code(r) == 'empty_file'


def test_missing_file_field(client, alice):
    r = client.post('/api/upload', data={'path': 'x'}, headers=alice[0], content_type='multipart/form-data')
    assert r.status_code == 400 and error_code(r) == 'missing_file'


def test_duplicate_upload_is_a_conflict_and_never_overwrites(client, alice, library_root):
    first = fake_mp4(100)
    assert upload(client, alice[0], first, 'a.mp4').status_code == 201
    r = upload(client, alice[0], fake_mp4(9999), 'a.mp4')
    assert r.status_code == 409 and error_code(r) == 'already_exists'
    assert (library_root / 'alice' / 'a.mp4').read_bytes() == first


def test_same_filename_for_two_users_is_fine(client, alice, bob, library_root):
    assert upload(client, alice[0], filename='a.mp4').status_code == 201
    assert upload(client, bob[0], filename='a.mp4').status_code == 201
    assert (library_root / 'alice' / 'a.mp4').exists() and (library_root / 'bob' / 'a.mp4').exists()


def test_a_file_dropped_into_the_library_by_other_means_is_not_overwritten(client, alice, library_root):
    (library_root / 'alice').mkdir(exist_ok=True)
    (library_root / 'alice' / 'pre.mp4').write_bytes(b'placed by an admin')
    r = upload(client, alice[0], filename='pre.mp4')
    assert r.status_code == 409
    assert (library_root / 'alice' / 'pre.mp4').read_bytes() == b'placed by an admin'


# --- limits -----------------------------------------------------------------------------

def test_size_limit(tmp_path):
    client = create_app(make_config(tmp_path, max_upload_mb=1)).test_client()
    register(client)
    headers = bearer(login(client).get_json()['access_token'])
    r = upload(client, headers, fake_mp4(2 * 1024 * 1024), 'big.mp4')
    assert r.status_code == 413
    assert upload(client, headers, fake_mp4(1000), 'small.mp4').status_code == 201


def test_per_user_quota(tmp_path):
    client = create_app(make_config(tmp_path, max_user_mb=1)).test_client()
    register(client)
    headers = bearer(login(client).get_json()['access_token'])
    assert upload(client, headers, fake_mp4(700 * 1024), 'a.mp4').status_code == 201
    r = upload(client, headers, fake_mp4(700 * 1024), 'b.mp4')
    assert r.status_code == 413 and error_code(r) == 'quota_exceeded'
    usage = client.get('/api/me', headers=headers).get_json()['usage']
    assert usage['videos'] == 1 and usage['quota_bytes'] == 1024 * 1024


# --- listing --------------------------------------------------------------------------------

def test_listing_shows_only_your_own_videos(client, alice, bob):
    upload(client, alice[0], filename='a1.mp4')
    upload(client, alice[0], filename='a2.mp4')
    upload(client, bob[0], filename='b1.mp4')

    mine = client.get('/api/videos', headers=alice[0]).get_json()
    assert mine['total'] == 2
    assert {v['path'] for v in mine['videos']} == {'alice/a1.mp4', 'alice/a2.mp4'}
    assert [v['path'] for v in client.get('/api/videos', headers=bob[0]).get_json()['videos']] == ['bob/b1.mp4']


def test_listing_is_newest_first_and_paginated(client, alice):
    for n in range(5):
        upload(client, alice[0], filename=f'v{n}.mp4')
    page = client.get('/api/videos?limit=2&offset=1', headers=alice[0]).get_json()
    assert [v['name'] for v in page['videos']] == ['v3.mp4', 'v2.mp4']
    assert page['total'] == 5 and page['limit'] == 2 and page['offset'] == 1


def test_listing_can_be_filtered_by_directory(client, alice):
    upload(client, alice[0], filename='a.mp4', path='trips')
    upload(client, alice[0], filename='b.mp4', path='trips/2026')
    upload(client, alice[0], filename='c.mp4', path='work')
    upload(client, alice[0], filename='d.mp4', path='trips_extra')     # '_' must not act as a LIKE wildcard
    names = lambda q: sorted(v['name'] for v in client.get(f'/api/videos?directory={q}', headers=alice[0]).get_json()['videos'])
    assert names('trips') == ['a.mp4', 'b.mp4']
    assert names('trips/2026') == ['b.mp4']
    assert names('nothing') == []


def test_listing_bad_paging_args(client, alice):
    assert client.get('/api/videos?limit=abc', headers=alice[0]).status_code == 400


def test_get_one_video(client, alice):
    upload(client, alice[0], filename='a.mp4', path='trips')
    r = client.get('/api/videos/alice/trips/a.mp4', headers=alice[0])
    assert r.status_code == 200 and r.get_json()['path'] == 'alice/trips/a.mp4'


def test_someone_elses_video_looks_exactly_like_a_missing_one(client, alice, bob):
    upload(client, alice[0], filename='secret.mp4')
    theirs = client.get('/api/videos/alice/secret.mp4', headers=bob[0])
    missing = client.get('/api/videos/bob/secret.mp4', headers=bob[0])
    assert theirs.status_code == missing.status_code == 404
    assert theirs.get_json() == missing.get_json()


def test_listing_requires_a_token(client):
    assert client.get('/api/videos').status_code == 401
