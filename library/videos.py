#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""Upload and list a user's videos, and hand back the URLs to play them.

Playing needs no account - CasterPak serves whatever is in the library to
anyone with the URL. Only writing and listing your own files does."""
import os

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from library.auth import current_user, lib
from library.errors import api_error
from library.models import Video, db
from library.storage import AlreadyExists, StorageError
from library.urls import embed_html, stream_urls
from library.validation import (ValidationError, sniff_matches_extension, validate_directory,
                                validate_upload_name)

bp = Blueprint('videos', __name__, url_prefix='/api')

MB = 1024 * 1024


def _iso(moment):
    if moment.tzinfo is None:               # SQLite hands back naive datetimes
        from datetime import timezone
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat().replace('+00:00', 'Z')


def video_to_dict(video: Video) -> dict:
    settings = lib().settings
    library_path = video.library_path
    urls = stream_urls(settings, library_path)
    directory, _, name = video.path.rpartition('/')
    return {
        'id': video.id,
        'path': library_path,
        'name': name,
        'directory': directory,
        'size': video.size_bytes,
        'created_at': _iso(video.created_at),
        'urls': urls,
        'embed_html': embed_html(urls['hls'], f"casterpak-video-{video.id}"),
    }


@bp.post('/upload')
@jwt_required()
def upload():
    user = current_user()
    if user is None:
        return api_error(401, 'invalid_token', 'the account no longer exists or is disabled')
    settings, storage = lib().settings, lib().storage

    upload_file = request.files.get('file')
    if upload_file is None:
        return api_error(400, 'missing_file', "send the video as multipart/form-data in a field named 'file'")

    try:
        filename = validate_upload_name(request.form.get('filename') or upload_file.filename,
                                        settings.allowed_extensions)
        directory = validate_directory(request.form.get('path'))
    except ValidationError as e:
        status = 415 if e.code == 'unsupported_type' else 422
        return api_error(status, e.code, e.message)

    stream = upload_file.stream
    header = stream.read(16)
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)

    if size == 0:
        return api_error(400, 'empty_file', 'the uploaded file is empty')
    if not sniff_matches_extension(header, filename):
        return api_error(415, 'not_a_video',
                         f"the contents of the file don't look like a .{filename.rsplit('.', 1)[-1]} video")
    if size > settings.max_upload_mb * MB:
        return api_error(413, 'file_too_large', f"the limit is {settings.max_upload_mb} MB per upload")
    if settings.max_user_mb:
        used = db.session.query(func.coalesce(func.sum(Video.size_bytes), 0)).filter(
            Video.user_id == user.id).scalar()
        if used + size > settings.max_user_mb * MB:
            return api_error(413, 'quota_exceeded',
                             f"this upload would exceed your {settings.max_user_mb} MB quota")

    relative_path = f"{directory}/{filename}" if directory else filename
    key = f"{user.username}/{relative_path}"
    if db.session.query(Video.id).filter_by(user_id=user.id, path=relative_path).first():
        return api_error(409, 'already_exists', f"{key} already exists; pick another name or path")

    try:
        written = storage.put(key, stream)
    except AlreadyExists:
        return api_error(409, 'already_exists', f"{key} already exists; pick another name or path")
    except StorageError as e:
        current_app.logger.error("upload of %s failed: %s", key, e)
        return api_error(503, 'storage_error', 'the video store is unavailable, try again later')

    video = Video(user_id=user.id, path=relative_path, size_bytes=written,
                  original_filename=(upload_file.filename or '')[:255] or None)
    db.session.add(video)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return api_error(409, 'already_exists', f"{key} already exists; pick another name or path")
    except Exception:
        # The file is stored but unindexed. Remove it rather than leave an
        # object nobody can list or count against a quota.
        db.session.rollback()
        try:
            storage.delete(key)
        except StorageError:
            current_app.logger.error("could not clean up %s after a failed index write", key)
        raise

    response = jsonify(video_to_dict(video))
    response.status_code = 201
    response.headers['Location'] = f"/api/videos/{key}"
    return response


@bp.get('/videos')
@jwt_required()
def list_videos():
    user = current_user()
    if user is None:
        return api_error(401, 'invalid_token', 'the account no longer exists or is disabled')

    try:
        limit = min(max(int(request.args.get('limit', 50)), 1), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except ValueError:
        return api_error(400, 'bad_request', 'limit and offset must be integers')

    query = Video.query.filter_by(user_id=user.id)
    try:
        directory = validate_directory(request.args.get('directory'))
    except ValidationError as e:
        return api_error(422, e.code, e.message)
    if directory:
        query = query.filter(Video.path.startswith(directory + '/', autoescape=True))

    total = query.count()
    videos = query.order_by(Video.created_at.desc(), Video.id.desc()).limit(limit).offset(offset).all()
    return jsonify({'videos': [video_to_dict(v) for v in videos],
                    'total': total, 'limit': limit, 'offset': offset})


@bp.get('/videos/<path:video_path>')
@jwt_required()
def get_video(video_path):
    user = current_user()
    if user is None:
        return api_error(401, 'invalid_token', 'the account no longer exists or is disabled')
    # Someone else's path, or one that doesn't exist, look identical: 404.
    prefix = user.username + '/'
    if not video_path.startswith(prefix):
        return api_error(404, 'not_found', 'no such video')
    video = Video.query.filter_by(user_id=user.id, path=video_path[len(prefix):]).first()
    if video is None:
        return api_error(404, 'not_found', 'no such video')
    return jsonify(video_to_dict(video))
