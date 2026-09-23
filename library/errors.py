#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""One error shape for the whole API:

    {"error": {"code": "invalid_path", "message": "human readable"}}

`code` is stable and meant for programs; `message` is meant for people."""
from flask import jsonify


def api_error(status: int, code: str, message: str, **extra):
    response = jsonify({'error': {'code': code, 'message': message, **extra}})
    response.status_code = status
    if status == 401:
        response.headers['WWW-Authenticate'] = 'Bearer'
    return response


def register_error_handlers(app):
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def http_error(e):
        code = {400: 'bad_request', 401: 'unauthorized', 403: 'forbidden', 404: 'not_found',
                405: 'method_not_allowed', 413: 'too_large', 415: 'unsupported_media_type'}.get(
            e.code, 'http_error')
        return api_error(e.code, code, e.description)

    @app.errorhandler(Exception)
    def unexpected(e):
        app.logger.exception("unhandled error")
        return api_error(500, 'internal_error', 'something went wrong on our side')
