#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import datetime as dt

import pytest
from flask_jwt_extended import create_access_token

from library import create_app
from library.models import User, db
from library.tests.conftest import PASSWORD, bearer, login, make_config, register


def error_code(response):
    return response.get_json()['error']['code']


# --- registration -------------------------------------------------------------

def test_register_creates_the_user_and_their_directory(client, library_root):
    r = register(client, 'alice', email='Alice@Example.com')
    assert r.status_code == 201
    user = r.get_json()['user']
    assert user['username'] == 'alice'
    assert user['email'] == 'alice@example.com'
    assert 'password' not in str(r.get_json())
    assert (library_root / 'alice').is_dir()


def test_password_is_hashed_at_rest(app, client):
    register(client, 'alice')
    with app.app_context():
        stored = User.query.filter_by(username='alice').one().password_hash
    assert PASSWORD not in stored
    assert stored.startswith(('scrypt:', 'pbkdf2:'))


@pytest.mark.parametrize('name', ['ab', 'Alice', 'has space', 'dots.no', '-lead', '_lead', 'a' * 33,
                                  '../x', 'x/y', '', None, 5])
def test_invalid_usernames_are_rejected(client, name):
    r = client.post('/api/users', json={'username': name, 'password': PASSWORD})
    assert r.status_code == 422
    assert error_code(r) == 'invalid_username'


@pytest.mark.parametrize('name', ['abr', 'api', 'admin', 'protected_media'])
def test_reserved_usernames_cannot_be_registered(client, name):
    """'abr' would make /i/abr/<x>/... ambiguous with CasterPak's own route."""
    r = register(client, name)
    assert r.status_code == 422
    assert error_code(r) == 'reserved_username'


@pytest.mark.parametrize('password', ['short', 'x' * 129, None, 12345678901234])
def test_bad_passwords_are_rejected(client, password):
    r = client.post('/api/users', json={'username': 'alice', 'password': password})
    assert r.status_code == 422


def test_password_may_not_equal_username(client):
    assert register(client, 'alicealice1', password='alicealice1').status_code == 422


def test_duplicate_username_and_email_conflict(client):
    assert register(client, 'alice', email='a@example.com').status_code == 201
    assert error_code(register(client, 'alice')) == 'username_taken'
    r = register(client, 'alice2', email='A@example.com')
    assert r.status_code == 409 and error_code(r) == 'email_taken'


def test_non_json_body_is_a_400(client):
    r = client.post('/api/users', data='username=alice', content_type='application/x-www-form-urlencoded')
    assert r.status_code == 400 and error_code(r) == 'invalid_json'


def test_closed_registration(tmp_path):
    client = create_app(make_config(tmp_path, registration='closed')).test_client()
    r = register(client)
    assert r.status_code == 403 and error_code(r) == 'registration_closed'


def test_invite_registration(tmp_path):
    client = create_app(make_config(tmp_path, registration='invite', registration_code='open-sesame-42')).test_client()
    assert error_code(register(client)) == 'invalid_invite_code'
    assert error_code(register(client, invite_code='wrong')) == 'invalid_invite_code'
    assert register(client, invite_code='open-sesame-42').status_code == 201


# --- login / tokens -----------------------------------------------------------

def test_login_returns_bearer_tokens(client, alice):
    _, body = alice
    assert body['token_type'] == 'Bearer'
    assert body['expires_in'] == 15 * 60
    assert body['access_token'] and body['refresh_token'] and body['user']['username'] == 'alice'


def test_login_is_case_insensitive_on_username(client):
    register(client, 'alice')
    assert login(client, 'ALICE').status_code == 200


def test_wrong_password_and_unknown_user_look_identical(client):
    register(client, 'alice')
    wrong_pw = login(client, 'alice', 'not the password')
    no_user = login(client, 'nobody', PASSWORD)
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.get_json() == no_user.get_json()
    assert wrong_pw.headers['WWW-Authenticate'] == 'Bearer'


def test_disabled_user_cannot_log_in_and_existing_tokens_stop_working(app, client, alice):
    headers, _ = alice
    with app.app_context():
        User.query.filter_by(username='alice').one().is_active = False
        db.session.commit()
    assert login(client, 'alice').status_code == 401
    assert client.get('/api/me', headers=headers).status_code == 401


def test_me_requires_a_token(client):
    r = client.get('/api/me')
    assert r.status_code == 401 and error_code(r) == 'missing_token'


def test_me(client, alice):
    r = client.get('/api/me', headers=alice[0])
    body = r.get_json()
    assert r.status_code == 200
    assert body['user']['username'] == 'alice'
    assert body['usage'] == {'videos': 0, 'bytes': 0, 'quota_bytes': None,
                             'max_upload_bytes': 2048 * 1024 * 1024,
                             'allowed_extensions': ['mp4', 'm4v', 'mov', 'mkv', 'webm']}


def test_garbage_token_is_rejected(client):
    r = client.get('/api/me', headers=bearer('not.a.jwt'))
    assert r.status_code == 401 and error_code(r) == 'invalid_token'


def test_token_signed_with_another_key_is_rejected(tmp_path):
    (tmp_path / 'a').mkdir()
    (tmp_path / 'b').mkdir()
    a = create_app(make_config(tmp_path / 'a', jwt_secret='A' * 40))
    b = create_app(make_config(tmp_path / 'b', jwt_secret='B' * 40))
    register(a.test_client())
    register(b.test_client())
    with a.app_context():
        forged = create_access_token(identity='1')
    r = b.test_client().get('/api/me', headers=bearer(forged))
    assert r.status_code == 401


def test_expired_access_token(app, client, alice):
    with app.app_context():
        expired = create_access_token(identity='1', expires_delta=dt.timedelta(seconds=-5))
    r = client.get('/api/me', headers=bearer(expired))
    assert r.status_code == 401 and error_code(r) == 'token_expired'


def test_refresh_gives_a_working_access_token(client, alice):
    _, body = alice
    r = client.post('/api/auth/refresh', headers=bearer(body['refresh_token']))
    assert r.status_code == 200
    assert client.get('/api/me', headers=bearer(r.get_json()['access_token'])).status_code == 200


def test_token_types_are_not_interchangeable(client, alice):
    headers, body = alice
    # an access token can't refresh...
    assert client.post('/api/auth/refresh', headers=headers).status_code == 401
    # ...and a refresh token can't be used as an access token.
    assert client.get('/api/me', headers=bearer(body['refresh_token'])).status_code == 401


def test_logout_revokes_the_refresh_token(client, alice):
    _, body = alice
    refresh = bearer(body['refresh_token'])
    assert client.post('/api/auth/logout', headers=refresh).status_code == 200
    r = client.post('/api/auth/refresh', headers=refresh)
    assert r.status_code == 401 and error_code(r) == 'token_revoked'


def test_health_is_public(client):
    r = client.get('/api/health')
    assert r.status_code == 200
    assert r.get_json() == {'status': 'ok', 'storage': 'filesystem', 'registration': 'open'}


def test_errors_are_json_even_for_unknown_routes(client):
    r = client.get('/api/nope')
    assert r.status_code == 404 and r.is_json and error_code(r) == 'not_found'


def test_cors_preflight_allows_the_authorization_header(client):
    r = client.options('/api/upload', headers={'Origin': 'https://blog.example.org',
                                               'Access-Control-Request-Method': 'POST',
                                               'Access-Control-Request-Headers': 'authorization'})
    assert r.status_code == 200
    # flask-cors answers '*' or echoes the caller's origin; both permit it
    assert r.headers['Access-Control-Allow-Origin'] in ('*', 'https://blog.example.org')
    assert 'authorization' in r.headers['Access-Control-Allow-Headers'].lower()
