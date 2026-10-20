#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Users and authentication.

Pre-built components, on purpose: Flask-JWT-Extended issues and verifies the
tokens, werkzeug.security hashes the passwords (scrypt), Flask-SQLAlchemy
holds the users. Nothing here invents crypto.

Tokens: a short-lived access token (sent as `Authorization: Bearer ...`) and a
long-lived refresh token that can only be exchanged for new access tokens, and
can be revoked by logging out. This is JWT bearer authentication - the shape
most clients (Plone included) already know - not a full OAuth2 authorization
server; see library/DESIGN.md for why, and for what adding one would take.
"""
import hmac
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (JWTManager, create_access_token, create_refresh_token,
                                get_jwt, get_jwt_identity, jwt_required)
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from library.errors import api_error
from library.models import RevokedToken, User, Video, db
from library.storage import StorageError
from library.validation import (ValidationError, validate_email, validate_password,
                                validate_username)

bp = Blueprint('auth', __name__, url_prefix='/api')
jwt = JWTManager()

_DUMMY_HASH = None


def _dummy_hash() -> str:
    """Checked when the username doesn't exist, so a wrong username and a
    wrong password take about the same time (no user enumeration by timing)."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = generate_password_hash('not-a-real-password')
    return _DUMMY_HASH


class Conflict(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def lib():
    return current_app.extensions['library']


def create_user(username: str, password: str, email=None) -> User:
    """Validate and create a user and their directory. Used by both the
    HTTP endpoint and the CLI, so the rules are the same either way."""
    settings = lib().settings
    username = validate_username(username, settings.reserved_usernames)
    email = validate_email(email)
    validate_password(password, username)

    if db.session.query(User.id).filter_by(username=username).first():
        raise Conflict('username_taken', f"the username '{username}' is taken")
    if email and db.session.query(User.id).filter_by(email=email).first():
        raise Conflict('email_taken', 'that email address is already registered')

    lib().storage.ensure_user_space(username)
    user = User(username=username, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise Conflict('username_taken', f"the username '{username}' is taken")
    return user


def current_user():
    """The User behind the request's token, or None if they no longer exist
    or have been deactivated (a still-valid token stops working at once)."""
    try:
        user = db.session.get(User, int(get_jwt_identity()))
    except (TypeError, ValueError):
        return None
    return user if user and user.is_active else None


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _token_response(user: User):
    settings = lib().settings
    claims = {'username': user.username}
    return {
        'token_type': 'Bearer',
        'access_token': create_access_token(identity=str(user.id), additional_claims=claims),
        'expires_in': settings.access_token_minutes * 60,
        'refresh_token': create_refresh_token(identity=str(user.id), additional_claims=claims),
        'user': user.to_dict(),
    }


# --- JWT plumbing -----------------------------------------------------------

@jwt.token_in_blocklist_loader
def _is_revoked(jwt_header, payload):
    if payload.get('type') != 'refresh':
        return False
    return db.session.query(RevokedToken.id).filter_by(jti=payload['jti']).first() is not None


@jwt.expired_token_loader
def _expired(jwt_header, payload):
    return api_error(401, 'token_expired', 'the token has expired; refresh it or log in again')


@jwt.invalid_token_loader
def _invalid(reason):
    return api_error(401, 'invalid_token', 'the token is not valid')


@jwt.unauthorized_loader
def _missing(reason):
    return api_error(401, 'missing_token', 'send an access token as "Authorization: Bearer <token>"')


@jwt.revoked_token_loader
def _revoked(jwt_header, payload):
    return api_error(401, 'token_revoked', 'this token was logged out')


# --- endpoints --------------------------------------------------------------

@bp.get('/health')
def health():
    s = lib()
    return jsonify({'status': 'ok', 'storage': s.storage.kind, 'registration': s.settings.registration})


@bp.post('/users')
def register():
    settings = lib().settings
    data = json_body()
    if data is None:
        return api_error(400, 'invalid_json', 'send a JSON object')

    if settings.registration == 'closed':
        return api_error(403, 'registration_closed',
                         'accounts are created by an administrator (flask --app library create-user)')
    if settings.registration == 'invite':
        given = data.get('invite_code')
        if not isinstance(given, str) or not hmac.compare_digest(given.encode(), settings.registration_code.encode()):
            return api_error(403, 'invalid_invite_code', 'a valid invite_code is required')

    try:
        user = create_user(data.get('username'), data.get('password'), data.get('email'))
    except ValidationError as e:
        return api_error(422, e.code, e.message)
    except Conflict as e:
        return api_error(409, e.code, e.message)
    except StorageError as e:
        current_app.logger.error("could not create user space: %s", e)
        return api_error(503, 'storage_error', 'the video store is unavailable')

    response = jsonify({'user': user.to_dict()})
    response.status_code = 201
    return response


@bp.post('/auth/login')
def login():
    data = json_body()
    if data is None:
        return api_error(400, 'invalid_json', 'send a JSON object')
    username, password = data.get('username'), data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or len(password) > 1024:
        return api_error(400, 'bad_request', 'username and password are required')

    user = User.query.filter_by(username=username.lower()).first()
    password_ok = check_password_hash(user.password_hash if user else _dummy_hash(), password)
    if not (user and password_ok and user.is_active):
        return api_error(401, 'invalid_credentials', 'wrong username or password')
    return jsonify(_token_response(user))


@bp.post('/auth/refresh')
@jwt_required(refresh=True)
def refresh():
    user = current_user()
    if user is None:
        return api_error(401, 'invalid_token', 'the account no longer exists or is disabled')
    settings = lib().settings
    return jsonify({
        'token_type': 'Bearer',
        'access_token': create_access_token(identity=str(user.id), additional_claims={'username': user.username}),
        'expires_in': settings.access_token_minutes * 60,
    })


@bp.post('/auth/logout')
@jwt_required(refresh=True)
def logout():
    """Revokes the refresh token it is called with. The (short-lived) access
    token already issued keeps working until it expires."""
    db.session.add(RevokedToken(jti=get_jwt()['jti']))
    db.session.commit()
    return jsonify({'status': 'logged out'})


@bp.get('/me')
@jwt_required()
def me():
    user = current_user()
    if user is None:
        return api_error(401, 'invalid_token', 'the account no longer exists or is disabled')
    settings = lib().settings
    count, used = db.session.query(func.count(Video.id), func.coalesce(func.sum(Video.size_bytes), 0)) \
        .filter(Video.user_id == user.id).one()
    return jsonify({
        'user': user.to_dict(),
        'usage': {
            'videos': count,
            'bytes': int(used),
            'quota_bytes': settings.max_user_mb * 1024 * 1024 or None,
            'max_upload_bytes': settings.max_upload_mb * 1024 * 1024,
            'allowed_extensions': list(settings.allowed_extensions),
        },
    })
