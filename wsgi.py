
import typing as t
import os

from flask import Flask
from flask import abort
from flask import send_from_directory
from werkzeug.security import safe_join
from markupsafe import escape

# setup logging - just import it.
import applogging

from config import config

import vodhls

app = Flask(__name__)

app.config.update(config)


@app.route('/')
def index():
    return """ homepage
           hello from flask
           """


@app.route('/i/<path:the_path>/index_0_av.m3u8')
def child_manifest(the_path: t.Union[os.PathLike, str]):
    if not vodhls.validate_path(the_path):
        abort(404)

    if not vodhls.manifest_exists(the_path + 'index_0_av.m3u8'):
        app.logger.debug(f"child manifest for {the_path} does not exist")
        vodhls.create_manifest_and_segments(the_path)

    app.logger.debug(f"returning {app.config['segmentParentPath']}/{the_path}/{app.config['childManifestFilename']}")

    filepath = the_path + '/' + config['childManifestFilename']

    return send_from_directory(directory=app.config['segmentParentPath'],
                               path=filepath,
                               mimetype="application/vnd.apple.mpegurl"
                               )


# HLS
@app.route('/i/<path:the_path>/<string:filename>.ts')
def segment(the_path, filename):
    filepath = the_path + '/' + filename + '.ts'
    return send_from_directory(directory=app.config['segmentParentPath'],
                               path=filepath,
                               mimetype="video/MP2T"
                               )


# DASH
@app.route('/i/<path:the_path>/figure/this/out/media.m3u8')
def dash(the_path):
    pass

