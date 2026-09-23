#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import configparser
import io
import pathlib

import pytest

from library import create_app

SECRET = 'test-secret-that-is-comfortably-longer-than-32-chars'
PASSWORD = 'correct horse battery'
ASSET = pathlib.Path(__file__).resolve().parents[2] / 'tests' / 'assets' / 'test-video.mp4'


def fake_mp4(size=2048) -> bytes:
    """Enough of an mp4 to pass the magic-byte check. Not playable."""
    return b'\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom' + b'\x00' * size


def make_config(tmp_path, **library):
    cfg = configparser.ConfigParser()
    root = tmp_path / 'library_root'
    root.mkdir(exist_ok=True)
    cfg['input'] = {'input_type': 'filesystem'}
    cfg['filesystem'] = {'videoParentPath': str(root)}
    cfg['library'] = {
        'jwt_secret': SECRET,
        'database_url': f"sqlite:///{tmp_path / 'library.db'}",
        'casterpak_url': 'https://video.example.test',
        'registration': 'open',
    }
    cfg['library'].update({k: str(v) for k, v in library.items()})
    return cfg


@pytest.fixture
def config(tmp_path):
    return make_config(tmp_path)


@pytest.fixture
def app(config):
    return create_app(config)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def library_root(config):
    return pathlib.Path(config['filesystem']['videoParentPath'])


def register(client, username='alice', password=PASSWORD, **extra):
    return client.post('/api/users', json={'username': username, 'password': password, **extra})


def login(client, username='alice', password=PASSWORD):
    return client.post('/api/auth/login', json={'username': username, 'password': password})


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def alice(client):
    """A registered, logged-in user: (auth headers, token response body)."""
    assert register(client, 'alice').status_code == 201
    body = login(client, 'alice').get_json()
    return bearer(body['access_token']), body


@pytest.fixture
def bob(client):
    assert register(client, 'bob').status_code == 201
    body = login(client, 'bob').get_json()
    return bearer(body['access_token']), body


def upload(client, headers, content=None, filename='clip.mp4', form=None, **fields):
    """`filename` is the name the file is sent as; `form` sets extra form fields
    (including a 'filename' override); other kwargs are form fields too."""
    content = fake_mp4() if content is None else content
    data = {'file': (io.BytesIO(content), filename), **fields, **(form or {})}
    return client.post('/api/upload', data=data, headers=headers, content_type='multipart/form-data')
