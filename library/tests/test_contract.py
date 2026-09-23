#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""The library and CasterPak never talk to each other - they agree on a
layout. These tests pin that agreement down from the library's side: whatever
it stores must be a path CasterPak's own validation accepts, at the location
CasterPak's own path rules resolve."""
import os

import pytest
from werkzeug.utils import safe_join

from pathsafety import validate_dirname, validate_filename
from library.tests.conftest import upload

CASES = [('clip.mp4', ''), ('clip.mp4', 'trips'), ('my.clip_v2+final.mp4', 'a/b/c'), ('X.MOV', '2026-09')]


@pytest.mark.parametrize('name, directory', CASES)
def test_stored_paths_pass_casterpaks_own_route_validation(client, alice, name, directory):
    body = upload(client, alice[0], filename=name, path=directory).get_json()
    # casterpak/routes.py: (dirname, filename) = os.path.split(dir_name); validate both.
    dirname, filename = os.path.split(body['path'])
    validate_dirname(dirname)
    validate_filename(filename)


@pytest.mark.parametrize('name, directory', CASES)
def test_the_file_is_where_casterpaks_filesystem_input_looks(client, alice, library_root, name, directory):
    body = upload(client, alice[0], filename=name, path=directory).get_json()
    # vodhls/media_manifest_filesystem.py: safe_join(videoParentPath, <path in the URL>)
    assert os.path.isfile(safe_join(str(library_root), body['path']))


@pytest.mark.parametrize('name, directory', CASES)
def test_urls_are_casterpaks_documented_routes(client, alice, name, directory):
    body = upload(client, alice[0], filename=name, path=directory).get_json()
    path = body['path']
    assert body['urls']['single'] == f'https://video.example.test/i/{path}/master.m3u8'
    assert body['urls']['abr'] == f'https://video.example.test/i/abr/{path}/master.m3u8'
    assert ' ' not in body['embed_html'].split('u = "')[1].split('"')[0]


def test_no_username_can_collide_with_a_casterpak_route_prefix(client):
    from library.tests.conftest import register
    for name in ('abr', 'api', 'protected_media', 'testing'):
        assert register(client, name).status_code == 422


def test_uploads_are_staged_outside_every_url_casterpak_can_serve(client, alice, library_root):
    from library.validation import ValidationError, validate_username
    upload(client, alice[0], filename='a.mp4')
    assert (library_root / '.incoming').is_dir()
    with pytest.raises(ValidationError):        # so '.incoming' can never be someone's username
        validate_username('.incoming', ())
