#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import datetime as dt

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    # Doubles as the user's directory name in the library, so it is validated
    # far more tightly than a filename - see validation.py.
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(254), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    videos = db.relationship('Video', back_populates='user', lazy='dynamic')

    def to_dict(self):
        return {'id': self.id, 'username': self.username, 'email': self.email,
                'created_at': self.created_at.isoformat()}


class Video(db.Model):
    """An index of what a user has uploaded. The bytes live in storage (the
    filesystem or S3); this row is what makes listing fast (no S3 LIST, no
    directory walk) and quota a SUM(). A file placed in the library by some
    other route is streamable but is not listed here."""
    __tablename__ = 'videos'
    __table_args__ = (db.UniqueConstraint('user_id', 'path', name='uq_video_user_path'),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    # Relative to the user's directory: 'trips/2026/holiday.mp4'
    path = db.Column(db.String(1024), nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship('User', back_populates='videos')

    @property
    def library_path(self) -> str:
        """The path CasterPak sees: '<username>/<path>'."""
        return f"{self.user.username}/{self.path}"


class RevokedToken(db.Model):
    """Refresh tokens that have been logged out. Only refresh tokens are ever
    revoked; access tokens are short-lived enough not to need it."""
    __tablename__ = 'revoked_tokens'

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
