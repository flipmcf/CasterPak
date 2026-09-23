#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
CasterPak Library: user accounts, upload, listing and embed URLs for the
library that CasterPak streams from.

This is a separate service from CasterPak (its own process, its own port),
built from the same repo and image. CasterPak stays a bring-your-own-library
streamer; this is the library you can bring. See library/DESIGN.md.

    gunicorn -c gunicorn.library.conf.py "library:create_app()"
    flask --app library run -p 5001            # development
"""
import os
import typing as t
from configparser import ConfigParser
from datetime import timedelta
from types import SimpleNamespace

from flask import Flask
from flask_cors import CORS
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from library.errors import register_error_handlers
from library.models import db
from library.settings import load_settings
from library.storage import storage_from_config


def create_app(config: t.Optional[ConfigParser] = None) -> Flask:
    if config is None:
        from config import get_config
        config = get_config()

    settings = load_settings(config)
    storage = storage_from_config(settings, config)

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=settings.database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        JWT_SECRET_KEY=settings.jwt_secret,
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=settings.access_token_minutes),
        JWT_REFRESH_TOKEN_EXPIRES=timedelta(days=settings.refresh_token_days),
        # A little headroom over the per-file limit for multipart framing;
        # the exact per-file limit is enforced in the upload endpoint.
        MAX_CONTENT_LENGTH=(settings.max_upload_mb + 1) * 1024 * 1024,
    )
    app.json.sort_keys = False
    app.extensions['library'] = SimpleNamespace(settings=settings, storage=storage)

    if settings.database_url.startswith('sqlite:///') and ':memory:' not in settings.database_url:
        os.makedirs(os.path.dirname(os.path.abspath(settings.database_url[len('sqlite:///'):])), exist_ok=True)

    db.init_app(app)
    from library.auth import bp as auth_bp, jwt
    from library.videos import bp as videos_bp
    jwt.init_app(app)
    app.register_blueprint(auth_bp)
    app.register_blueprint(videos_bp)
    register_error_handlers(app)

    # Bearer-token API: no cookies, so no ambient credentials for another
    # site to abuse - a permissive CORS default is safe. Tighten with
    # [library] cors_origins for a known front-end.
    origins = '*' if settings.cors_origins == ('*',) else list(settings.cors_origins)
    CORS(app, resources={r'/api/*': {'origins': origins}},
         allow_headers=['Authorization', 'Content-Type'], expose_headers=['Location'])

    with app.app_context():
        if db.engine.dialect.name == 'sqlite':
            @event.listens_for(db.engine, 'connect')
            def _sqlite_pragmas(dbapi_connection, _record):
                cursor = dbapi_connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL')
                cursor.execute('PRAGMA busy_timeout=15000')
                cursor.close()
        try:
            db.create_all()
        except OperationalError:
            # Several gunicorn workers starting at once can race to create
            # the tables; whoever lost finds them already there.
            db.session.rollback()

    from library.cli import register_cli
    register_cli(app)
    return app
