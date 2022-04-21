
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


@app.route('/i/<path:dir_name>/index_0_av.m3u8')
def child_manifest(dir_name: t.Union[os.PathLike, str]):
    if not vodhls.validate_path(dir_name):
        abort(404)

    if not vodhls.manifest_exists(dir_name + 'index_0_av.m3u8'):
        app.logger.debug(f"child manifest for {dir_name} does not exist")
        vodhls.create_manifest_and_segments(dir_name)

    app.logger.debug(f"returning {app.config['segmentParentPath']}/{dir_name}/{app.config['childManifestFilename']}")

    filepath = dir_name + '/' + config['childManifestFilename']

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

