#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#BSD 3-Clause License
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import typing as t
import os
import re

from flask import Flask
from flask import abort
from flask import send_from_directory, send_file
from flask import url_for

import applogging
import logging
from logging.config import dictConfig

from config import get_config
from vodhls import EncodingError
from vodhls.factory import vodhls_media_playlist_factory, vodhls_master_playlist_factory
import cachedb

# valid characters in a filename
filenameRE = re.compile(r'[^.a-zA-Z\d_-]')
# valid characters in a directory path:
dirnameRE = re.compile(r'[^.a-zA-Z\d_/-]')

def setup_app(app, base_config):
    logging_config = applogging.CASTERPAK_DEFAULT_LOGGING_CONFIG
    dictConfig(logging_config)

    if base_config.getboolean('application', 'debug'):
        app.config['DEBUG'] = True
        app.logger.debug(f"flask debugging on")

    app.config.update(base_config)
    if base_config['output'].get('serverName'):
        app.logger.info(f"casterpak server name is {base_config['output'].get('serverName')} ")

        # # NOT SETTING APP SERVER NAME - AWS LOAD BALANCER CANNOT SET HOST HEADER
        # app.config['SERVER_NAME'] = base_config['output']['serverName']
        app.logger.info("flask app server name not set")

    # initialize segment directory
    if not os.path.isdir(app.config['output']['segmentParentPath']):
        os.mkdir(app.config['output']['segmentParentPath'])
        app.logger.debug(f"created new output directory {app.config['output']['segmentParentPath']}")
    app.logger.info(f"output directory set to {app.config['output']['segmentParentPath']}")

    # initialize input cache directory
    if app.config['input']['input_type'] == 'filesystem' and \
            app.config['filesystem'].getboolean('cache_input') is False:
        app.logger.debug("input caching disabled")
        pass

    else:
        if not os.path.isdir(app.config['input']['videoCachePath']):
            os.mkdir(app.config['input']['videoCachePath'])
            app.logger.debug(f"created new input cache directory {app.config['input']['videoCachePath']}")
        app.logger.info("input caching enabled")
        app.logger.info(f"input caching to {app.config['input']['videoCachePath']}")


def setup_gunicorn_logging(base_config):
    vodhls_logger = logging.getLogger('vodhls')
    gunicorn_error_logger = logging.getLogger('gunicorn.error')

    formatter = logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] in gunicorn: %(message)s')
    for handler in gunicorn_error_logger.handlers:
        handler.setFormatter(formatter)

    formatter = logging.Formatter(fmt='[%(asctime)s] [%(levelname)s] in %(module)s: %(message)s')
    app.logger.handlers = gunicorn_error_logger.handlers.copy()
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

    vodhls_logger.handlers = gunicorn_error_logger.handlers.copy()
    for handler in app.logger.handlers:
        handler.setFormatter(formatter)

    if base_config['application'].getboolean('debug'):
        gunicorn_error_logger.setLevel(logging.DEBUG)

    app.logger.debug("Debug Enabled")
    app.logger.info("Info log Enabled")


app_config = get_config()
app = Flask(__name__)
if __name__ != "__main__":
    setup_gunicorn_logging(app_config)

setup_app(app, app_config)


def get_base_url(dir_name: t.Union[os.PathLike, str]) -> str:
    # if there is a servername configured, use absolute url's

    # We would prefer to use the flask 'url_for('mp4_file')' here, but unfortunately SERVER_NAME also creates
    #  routing in Flask
    # This leads to errors -
    # if SERVER_NAME is not set, routing is correct (no 404)
    #     but the m3u8 output files contain the wrong hostnames
    # IF SERVER_NAME is set, then routing breaks and everything is a 404.

    # so, we will not use url_for but hard-code the url to the mp4_file here as our base-url
    # if app.config['output'].get('serverName', None):
        # baseurl = url_for('mp4_file', dir_name=dir_name, _external=True)
        # baseurl = baseurl + '/'
    # otherwise, use relative url's

    if app_config['output'].get('serverName'):
        # this is basically re-typing the path decorator for mp4_file()
        baseurl = f"https://{app_config['output'].get('serverName')}/i/{dir_name}/"
    else:
        baseurl = ''

    return baseurl


@app.route('/i/<path:dir_name>')
def mp4_file(dir_name: t.Union[os.PathLike, str]):
    """Path directly to MP4 file, without a stream"""

    # This route is not supported.  The route is only here to construct URLs
    app.logger.debug(f"caught 404 for {dir_name}")
    abort(404)


@app.route('/i/<path:dir_name>/master.m3u8')
def single_bitrate_manifest(dir_name: str):
    """ creates a variant manifest containing a single bitrate file """

    (dirname, filename) = os.path.split(dir_name)

    #sanitize
    filename = filenameRE.sub('', filename)
    dirname = dirnameRE.sub('', dirname)

    files = [os.path.join(dirname, filename), ]

    vodhls_manager = vodhls_master_playlist_factory(files, dirname)

    if not vodhls_manager.manifest_exists():
        vodhls_manager.set_baseurl(get_base_url(dirname))

        try:
            vodhls_manager.output_hls()
        except FileNotFoundError:
            abort(404)

    return send_from_directory(directory=vodhls_manager.output_dir,
                               path=vodhls_manager.master_playlist_name,
                               mimetype="application/vnd.apple.mpegurl")


@app.route('/i/<path:csmil_str>.csmil/master.m3u8')
def csmil_parent_manifest(csmil_str: str):
    # TODO this needs to be seriously refactored and decoupled from the flask app.
    """Create a master variant manifest.
       This follows the old akamai pattern for Media Services On Demand to specify a list of renditions

       https://example.com/i/<common_filename_prefix>,<bitrate>,<bitrate>,<bitrate>,<bitrate>,<common_filename_suffix>.csmil/manifest.m3u8

       For example:
       https://example.com/i/20190315/1475/1_0yr7lkwq_1_,lcrv4ssw,h8eu9lpn,bzzbs232,xf8strxb,_1.mp4.csmil/manifest.m3u8

       will request files:
       20190315/1475/1_0yr7lkwq_1_lcrv4ssw_1.mp4
       20190315/1475/1_0yr7lkwq_1_h8eu9lpn_1.mp4
       20190315/1475/1_0yr7lkwq_1_bzzbs232_1.mp4
       20190315/1475/1_0yr7lkwq_1_xf8strxb_1.mp4

       And create a hls manifest for them.
    """

    # create file list from url:
    csmil_chunks = csmil_str.split('/')
    dirs = csmil_chunks[:-1]
    files = csmil_chunks[-1]
    file_chunks = files.split(',')

    #filenameRE is our sanitizer.  See above at module-level for definition.
    dirs = [filenameRE.sub('', d) for d in dirs]
    common_filename_prefix = filenameRE.sub('', file_chunks[0])
    bitrates = [filenameRE.sub('', f) for f in file_chunks[1:-1]]
    common_filename_suffix = filenameRE.sub('', file_chunks[-1])

    dir = os.path.join(*dirs)
    filenames = [common_filename_prefix+bitrate+common_filename_suffix for bitrate in bitrates]
    files = [os.path.join(dir, filename) for filename in filenames]
    vodhls_manager = vodhls_master_playlist_factory(files, dir)

    if not vodhls_manager.manifest_exists():
        vodhls_manager.set_baseurl(get_base_url(dir))

        try:
            vodhls_manager.output_hls()
        except FileNotFoundError:
            abort(404)

        # casterpak is responsible for adding these segments to the cacheDB
        for manager in vodhls_manager.segment_managers:

            # This shouldn't be here - the manager status should be abstracted away in vodhls
            if manager['status'] != 'ready':
                continue

            # Again, we shouldn't have to subscript to get the actual manager.
            segment_dir_name = manager['segment_manager'].filename
            db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
            db.addrecord(filename=segment_dir_name)

    return send_from_directory(directory=vodhls_manager.output_dir,
                               path=vodhls_manager.master_playlist_name,
                               mimetype="application/vnd.apple.mpegurl")


# TODO this hard-codes the childManifestFilename which should be set in config.ini
@app.route('/i/<path:dir_name>/index_0_av.m3u8')
def child_manifest(dir_name: t.Union[os.PathLike, str]):
    """

    :param dir_name:  path to an input mp4 file relative to the configured video input directory
    :return: http reply for an hls media manifest
    """

    #sanitize
    dir_name = dirnameRE.sub('', dir_name)

    try:
        hls_manager = vodhls_media_playlist_factory(dir_name)
    except FileNotFoundError:
        app.logger.info(f'hls_manager failed to initialize for {dir_name}')
        abort(404)
        return
    except (NotImplementedError, ValueError) as e:
        app.logger.info(f'{str(e)}')
        abort(500)
        return

    hls_manager.set_baseurl(get_base_url(dir_name))

    # cache check
    if not hls_manager.manifest_exists():
        try:
            # CONSIDER returning an HTTP 202 here if hls_manager.create() is expected to take a while
            # Clients might not be able to properly react to a 202 just yet, but maybe in the future...
            child_manifest_filename = hls_manager.create()
        except EncodingError:
            abort(500)
            return
        except FileNotFoundError:
            abort(404)
            return
    else:
        child_manifest_filename = hls_manager.output_manifest_filename

    app.logger.debug(f"returning {child_manifest_filename}")

    # record successful access for caching
    db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
    db.addrecord(filename=dir_name)

    return send_file(child_manifest_filename,
                     mimetype="application/vnd.apple.mpegurl")


# HLS
@app.route('/i/<path:dir_name>/<string:filename>.ts')
def segment(dir_name: t.Union[os.PathLike, str], filename: str):
    filename = filename + '.ts'
    filepath = dir_name + '/' + filename

    #sanitize
    filename = filenameRE.sub('', filename)
    filepath = dirnameRE.sub('', filepath)

    # create instance of vodhls manager
    try:
        hls_manager = vodhls_media_playlist_factory(dir_name)
    except FileNotFoundError:
        abort(404)
        return

    if not hls_manager.segment_exists(filename):
        app.logger.info(f"request for segment {filepath} that does not exist. creating manifest")

        hls_manager.set_baseurl(get_base_url(dir_name))
        try:
            child_manifest_filename = hls_manager.create()
        except EncodingError:
            abort(500)
            return

    # record successful access for caching
    db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
    db.addrecord(filename=dir_name)

    return send_from_directory(directory=app.config['output']['segmentParentPath'],
                               path=filepath,
                               mimetype="video/MP2T"
                               )


# DASH
@app.route('/i/<path:dir_name>/figure/this/out/media.m3u8')
def dash(dir_name: t.Union[os.PathLike, str]):
    app.logger.debug(f"calling dash with {dir_name}")
    raise NotImplementedError

