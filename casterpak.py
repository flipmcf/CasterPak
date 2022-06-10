import typing as t
import os

from flask import Flask
from flask import abort
from flask import send_from_directory, send_file
from flask import url_for

# setup logging - just import it.
import applogging
import logging
from logging.config import dictConfig

from config import get_config
import vodhls
import cachedb


def setup_app(app, base_config):
    from logging.config import dictConfig
    logging_config = applogging.CASTERPAK_DEFAULT_LOGGING_CONFIG
    dictConfig(logging_config)

    if base_config.getboolean('application', 'debug'):
        app.config['DEBUG'] = True
        app.logger.debug(f"flask debugging on")

    app.config.update(base_config)
    if base_config['output'].get('serverName'):
        app.config['SERVER_NAME'] = base_config['output']['serverName']
    app.logger.info(f"server name: {app.config['SERVER_NAME']}")

    # initialize segment directory
    if not os.path.isdir(app.config['output']['segmentParentPath']):
        os.mkdir(app.config['output']['segmentParentPath'])
        app.logger.debug(f"created new output directory {app.config['output']['segmentParentPath']}")
    app.logger.info(f"output directory set to {app.config['output']['segmentParentPath']}")

    # initialize input cache directory
    if app.config['cache'].getboolean('cache_input'):
        if not os.path.isdir(app.config['input']['videoCachePath']):
            os.mkdir(app.config['input']['videoCachePath'])
            app.logger.debug(f"created new input cache directory {app.config['input']['videoCachePath']}")
        app.logger.info("input caching enabled")
        app.logger.info(f"input caching to {app.config['input']['videoCachePath']}")


def setup_gunicorn_logging(base_config):
    vodhls_logger = logging.getLogger('vodhls')
    gunicorn_error_logger = logging.getLogger('gunicorn.error')

    app.logger.handlers = gunicorn_error_logger.handlers
    vodhls_logger.handlers = gunicorn_error_logger.handlers

    if base_config['application'].getboolean('debug'):
        gunicorn_error_logger.setLevel(logging.DEBUG)

    app.logger.debug("Debug Enabled")
    app.logger.info("Info log Enabled")

app_config = get_config()

app = Flask(__name__)
setup_app(app, app_config)

if __name__ != "__main__":
    setup_gunicorn_logging(app_config)


@app.route('/i/<path:dir_name>')
def mp4_file(dir_name: t.Union[os.PathLike, str]):
    """Path directly to MP4 file, without a stream"""

    # This route is not supported.  The route is only here to construct URLs
    abort(404)


# TODO this hard-codes the childManifestFilename which should be set in config.ini
@app.route('/i/<path:dir_name>/index_0_av.m3u8')
def child_manifest(dir_name: t.Union[os.PathLike, str]):
    # create instance of vodhls manager
    try:
        hls_manager = vodhls.VODHLSManager(dir_name)
    except FileNotFoundError:
        app.logger.info(f'hls_manager failed to initialize for {dir_name}')
        abort(404)
        return

    # TODO: refactor duplicate code
    # if there is a servername configured, use absolute url's
    if app.config['output'].get('serverName', None):
        baseurl = url_for('mp4_file', dir_name=dir_name, _external=True)
        baseurl = baseurl + '/'
    # otherwise, use relative url's
    else:
        baseurl = ''

    hls_manager.set_baseurl(baseurl)

    # cache check
    if not hls_manager.manifest_exists():
        try:
            child_manifest_filename = hls_manager.create()
        except vodhls.EncodingError:
            abort(500)
            return
    else:
        child_manifest_filename = hls_manager.output_manifest_filename

    app.logger.debug(f"returning {child_manifest_filename}")

    # record successful access for caching
    db = cachedb.CacheDB()
    db.addrecord(filename=dir_name)

    return send_file(child_manifest_filename,
                     mimetype="application/vnd.apple.mpegurl")


# HLS
@app.route('/i/<path:dir_name>/<string:filename>.ts')
def segment(dir_name: t.Union[os.PathLike, str], filename):
    filename = filename + '.ts'
    filepath = dir_name + '/' + filename

    # create instance of vodhls manager
    try:
        hls_manager = vodhls.VODHLSManager(dir_name)
    except FileNotFoundError:
        abort(404)
        return

    if not hls_manager.segment_exists(filename):
        app.logger.info(f"request for segment {filepath} that does not exist. creating manifest")

        # TODO: refactor duplicate code
        # if there is a servername configured, use absolute url's
        if app.config['output'].get('serverName', None):
            baseurl = url_for('mp4_file', dir_name=dir_name, _external=True)
            baseurl = baseurl + '/'
        # otherwise, use relative url's
        else:
            baseurl = ''

        hls_manager.set_baseurl(baseurl)
        try:
            child_manifest_filename = hls_manager.create()
        except vodhls.EncodingError:
            abort(500)
            return

    # record successful access for caching
    db = cachedb.CacheDB()
    db.addrecord(filename=dir_name)

    return send_from_directory(directory=app.config['output']['segmentParentPath'],
                               path=filepath,
                               mimetype="video/MP2T"
                               )


# DASH
@app.route('/i/<path:dir_name>/figure/this/out/media.m3u8')
def dash(dir_name):
    app.logger.debug(f"calling dash with {dir_name}")
    raise NotImplementedError
