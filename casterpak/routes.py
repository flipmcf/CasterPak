import os
import typing as t

from flask import Blueprint, Response
from flask import abort, current_app, send_from_directory, send_file, make_response, redirect

from werkzeug.utils import safe_join

import cachedb
from vodhls import EncodingError
from vodhls.csmil import CsmilDescriptor
from vodhls.factory import (vodhls_master_playlist_factory,
                            vodhls_media_playlist_factory)

from vodhls.csmil import CsmilDescriptor
from encoding import EncodingManager
from encoding import EncodingAlreadyInProgressError, EncodingManagerError
from jit import jit_manager_factory
from pathsafety import validate_filename, validate_dirname, InvalidPathError

bp = Blueprint('casterpak', __name__)


def get_base_url(dir_name: t.Union[os.PathLike, str]) -> str:
    app_config = current_app.config
    if app_config['output'].get('serverName'):
        if app_config['output'].get('use_https'):
            protocol = 'https'
        else:
            protocol = 'http'
        baseurl = f"{protocol}://{app_config['output'].get('serverName')}/i/"
        if dir_name:
            baseurl += dir_name + '/'
    else:
        baseurl = ''

    return baseurl

@bp.route('/i/<path:dir_name>')
def mp4_file(dir_name: t.Union[os.PathLike, str]):
    """Path directly to MP4 file, without a stream"""
    current_app.logger.debug(f"caught 404 for {dir_name}")
    abort(404)


@bp.route('/i/<path:dir_name>/master.m3u8')
def single_bitrate_manifest(dir_name: str):
    """ creates a master manifest containing only one URI to a single bitrate """

    (dirname, filename) = os.path.split(dir_name)

    try:
        validate_dirname(dirname)
        validate_filename(filename)
    except InvalidPathError as e:
        return abort(422, description=str(e))

    basename, ext = os.path.splitext(filename)

    # a single-bitrate stream is a CsmilDescriptor with exactly one, unlabeled
    # rendition -- the bare source file itself, with no bitrate suffix.
    csmil = CsmilDescriptor(dirname=dirname, basename=basename, ext=ext, bitrates=[''])

    vodhls_manager = vodhls_master_playlist_factory(csmil)

    if not vodhls_manager.manifest_exists():
        vodhls_manager.set_baseurl(get_base_url(dirname))

        try:
            vodhls_manager.output_hls()
        except FileNotFoundError:
            abort(404)

    return send_from_directory(directory=vodhls_manager.output_dir,
                               path=vodhls_manager.master_playlist_name,
                               mimetype="application/vnd.apple.mpegurl")


@bp.route('/i/abr/<path:dir_name>/master.m3u8')
def abr_manifest(dir_name: str):
    """
    This endpoint acts as the State Manager. 
    1. encodings do not exist
           a. start background ABR transcodes (cpu killer)
           b. starts JIT encode, and returns emergency stream. (sub optimal playback)
    2. encodings currently in progress
           return the emergency stream.
    3. encodings exist
           redirect to CSMIL. 
        
    """
    
    #determine output dir for segments
    (dirname, filename) = os.path.split(dir_name)

    try:
        validate_dirname(dirname)
        validate_filename(filename)
    except InvalidPathError as e:
        return abort(422, description=str(e))

    basename, ext = os.path.splitext(filename)

    #determine input directory for original video file.
    localdir = current_app.config['filesystem']['videoParentPath']
    video_file = safe_join(localdir, dir_name)
    if video_file is None:
        # dir_name already passed validate_dirname/validate_filename above,
        # so this should be unreachable - but safe_join returns None rather
        # than raising, and a silent None here would crash downstream with
        # a bare TypeError (os.path.split(None)) instead of a clean 422.
        return abort(422, description="Invalid filename")

    current_app.logger.info(f"abr route called for {video_file}")

    encoder = EncodingManager(video_file)
    try:
        #State 3 - encodings already exist.
        if encoder.renditions_exist():
            current_app.logger.info(f"renditions exist - redirect to csmil")
            # TIER 2: Encodings are ready. Redirect to stateless CSMIL delivery.
            transcodes_dir = os.path.join(dirname, f"{filename}.transcodes")
            csmil = CsmilDescriptor(transcodes_dir, basename, ext, encoder.bitrates)
            redirect_url = f"/i/{csmil.csmil_string}.csmil/master.m3u8"
            return redirect(redirect_url, code=302)

        # State 1 or 2 - no encodings exist, or they are in process.
        else:
            # TIER 3: No encodings exist. Emergency

            # First (why first?) We queue up the quality ABR encoding process.
            try:
                encoder.queue_background_encoding()
            except EncodingAlreadyInProgressError:
                current_app.logger.info("ABR encoding already queued, not queuing another.")
            except EncodingManagerError as e:
                current_app.logger.error(f"Error queuing ABR encoding: {e}")

            #We then will provide the JIT stream until the real stream is ready (state 3 above)
            hls_manager = vodhls_media_playlist_factory(dir_name)
            jit_manager = jit_manager_factory(dir_name=dir_name,
                                              input_filepath=hls_manager.source_file,
                                              output_dir=hls_manager.output_dir,
                                              manifest_path=hls_manager.output_manifest_filename)

            if jit_manager.first_segment_exists():
                current_app.logger.info("JIT stream already exists, returning it")
            else:
                current_app.logger.info("Starting lightweight JIT stream encoding")
                #this will block until the first segment is created, or timeout occurs.
                jit_manager.trigger_jit_encoding()
            
            # Return a dynamic Master Manifest pointing to the new JIT stream
            child_url = jit_manager.get_m3u8_index_url() # something like f"/i/{dir_name}/index_0_av.m3u8"
            m3u8_text = (
                "#EXTM3U\n"
                "#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=854x480\n"
                f"{child_url}\n"
            )
            
            return Response(m3u8_text, mimetype='application/vnd.apple.mpegurl')

    except FileNotFoundError:
        return abort(404, description="Original source video at videoParentPath/{dir_name} not found.")
    except Exception as e:
        return abort(504, description=f"Encoding failed: {e}")

# TODO rename function to 'csmil_master_manifest' to keep naming convention of 'master playlist'
@bp.route('/i/<path:csmil_str>.csmil/master.m3u8')
def csmil_parent_manifest(csmil_str: str):
    """
    creates a master manifest containing multiple bitrate files.

    This is useful when the renditions are already available, and are in an arbitrary naming format.
    This is the path that /abr/ will redirect to if it finds that renditions exist.
    """

    try:
        csmil_data = CsmilDescriptor.from_string(csmil_str)
    except InvalidPathError as e:
        return abort(422, description=str(e))

    vodhls_manager = vodhls_master_playlist_factory(csmil_data)

    if not vodhls_manager.manifest_exists():
        vodhls_manager.set_baseurl(get_base_url(csmil_data.dirname))
        try:
            vodhls_manager.output_hls()
        except FileNotFoundError:
            abort(404)

        for manager in vodhls_manager.segment_managers:
            if manager['status'] != 'ready':
                continue
            segment_dir_name = manager['segment_manager'].filename
            db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
            db.addrecord(filename=segment_dir_name)

    
    return send_from_directory(directory=vodhls_manager.output_dir,
                               path=vodhls_manager.master_playlist_name,
                               mimetype="application/vnd.apple.mpegurl")


@bp.route('/i/<path:dir_name>/index_0_av.m3u8')
def child_manifest(dir_name: t.Union[os.PathLike, str]):
    try:
        validate_dirname(dir_name)
    except InvalidPathError as e:
        return abort(422, description=str(e))

    try:
        hls_manager = vodhls_media_playlist_factory(dir_name)
    except FileNotFoundError:
        current_app.logger.info(f'hls_manager failed to initialize for {dir_name}')
        abort(404)
    except (NotImplementedError, ValueError) as e:
        current_app.logger.info(f'{str(e)}')
        abort(500)

    hls_manager.set_baseurl(get_base_url(dir_name))

    if not hls_manager.manifest_exists():
        try:
            hls_manager.create()
        except EncodingError:
            abort(500)
        except FileNotFoundError:
            abort(404)

    db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
    db.addrecord(filename=dir_name)

    return send_file(hls_manager.output_manifest_filename,
                     mimetype="application/vnd.apple.mpegurl")


@bp.route('/i/<path:dir_name>/<string:filename>.ts')
def segment(dir_name: t.Union[os.PathLike, str], filename: str):
    filename = filename + '.ts'
    filepath = dir_name + '/' + filename

    try:
        validate_dirname(dir_name)
        validate_filename(filename)
    except InvalidPathError as e:
        return abort(422, description=str(e))

    try:
        hls_manager = vodhls_media_playlist_factory(dir_name)
    except FileNotFoundError:
        abort(404)

    # Create the stream if it's missing.
    if not hls_manager.segment_exists(filename):
        current_app.logger.info(f"request for segment {filepath} that does not exist. creating manifest")

        hls_manager.set_baseurl(get_base_url(dir_name))
        try:
            hls_manager.create()
        except EncodingError:
            abort(500)


    # track the hit to keep the cache fresh.
    db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
    db.addrecord(filename=dir_name)

    if current_app.config['output'].getboolean('behind_nginx', fallback=False):
        # Nginx Handoff: return an empty body, and tell nginx where the file is
        # located internally (see nginx/conf.d/default.conf, location /protected_media/).
        # This path must match the internal location block in nginx.conf
        response = make_response("")
        response.headers['Content-Type'] = 'video/MP2T'
        response.headers['X-Accel-Redirect'] = f"/protected_media/{filepath}"
        return response
    else:
        # No reverse proxy in front (bare flask/gunicorn) - serve the file ourselves.
        segment_parent_path = current_app.config['output']['segmentParentPath']
        return send_from_directory(segment_parent_path, filepath, mimetype='video/MP2T')

@bp.route('/d/<path:dir_name>/figure/this/out/media.m3u8')
def dash(dir_name: t.Union[os.PathLike, str]):
    current_app.logger.debug(f"calling dash with {dir_name}")
    raise NotImplementedError

@bp.route('/c/<path:dir_name>/figure/this/out/media.m3u8')
def cmaf(dir_name: t.Union[os.PathLike, str]):
    current_app.logger.debug(f"calling cmaf with {dir_name}")
    raise NotImplementedError
