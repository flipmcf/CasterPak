import typing as t
import os

from flask import Flask
from flask import abort
from flask import send_from_directory
from flask import url_for

# setup logging - just import it.
import applogging

from config import get_config
import vodhls
import cachedb

app = Flask(__name__)
base_config = get_config()
app.config.update(base_config)
if base_config['output'].get('serverName'):
    app.config['SERVER_NAME'] = base_config['output']['serverName']

if base_config['application'].get('debug'):
    app.config['DEBUG'] = True


@app.route('/i/<path:dir_name>')
def mp4_file(dir_name: t.Union[os.PathLike, str]):
    """Path directly to MP4 file, without a stream"""

    # This route is not supported.  The route is only here to construct URLs
    abort(404)


# TODO this hard-codes the childManifestFilename which should be set in config.ini
@app.route('/i/<path:dir_name>/index_0_av.m3u8')
def child_manifest(dir_name: t.Union[os.PathLike, str]):
    if not vodhls.validate_path(dir_name):
        abort(404)

    # TODO: refactor duplicate code
    # if there is a servername configured, use absolute url's
    if app.config['output'].get('serverName', None):
        baseurl = url_for('mp4_file', dir_name=dir_name, _external=True)
        baseurl = baseurl + '/'
    # otherwise, use relative url's
    else:
        baseurl = ''

    if not vodhls.manifest_exists(os.path.join(dir_name, app.config['output']['childManifestFilename'])):
        app.logger.debug(f"child manifest for {dir_name} does not exist, creating")
        vodhls.create_manifest_and_segments(dir_name, baseurl)

    app.logger.debug(f"returning {app.config['output']['segmentParentPath']}/"
                     f"{dir_name}/{app.config['output']['childManifestFilename']}")

    filepath = dir_name + '/' + app.config['output']['childManifestFilename']

    # record successful access for caching
    db = cachedb.CacheDB()
    db.addrecord(filename=dir_name)

    return send_from_directory(directory=app.config['output']['segmentParentPath'],
                               path=filepath,
                               mimetype="application/vnd.apple.mpegurl"
                               )


# HLS
@app.route('/i/<path:dir_name>/<string:filename>.ts')
def segment(dir_name: t.Union[os.PathLike, str], filename):
    filepath = dir_name + '/' + filename + '.ts'

    if not vodhls.segment_exists(filepath):
        app.logger.info(f"request for segment {filepath} that does not exist. creating manifest")

        # TODO: refactor duplicate code
        # if there is a servername configured, use absolute url's
        if app.config['output'].get('serverName', None):
            baseurl = url_for('mp4_file', dir_name=dir_name, _external=True)
            baseurl = baseurl + '/'
        # otherwise, use relative url's
        else:
            baseurl = ''

        retcode = vodhls.create_manifest_and_segments(dir_name, baseurl)
        if not retcode:
            abort(500, "failure creating stream")

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
