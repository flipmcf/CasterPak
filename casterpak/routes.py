import os
import re
import typing as t
import subprocess
import time

from flask import Blueprint, Response
from flask import abort, current_app, send_from_directory, send_file, make_response, redirect

from werkzeug.utils import safe_join

import cachedb
from vodhls import EncodingError
from vodhls.csmil import CsmilDescriptor
from vodhls.factory import (vodhls_master_playlist_factory,
                            vodhls_media_playlist_factory)

from encoding import EncodingManager


## TODO - this is duplicated in vodhls/csmil.py
# valid characters in a filename
filenameRE = re.compile(r'[^.a-zA-Z\d_-]')
# valid characters in a directory path:
dirnameRE = re.compile(r'[^.a-zA-Z\d_/-]')

bp = Blueprint('casterpak', __name__)


def get_base_url(dir_name: t.Union[os.PathLike, str]) -> str:
    app_config = current_app.config
    if app_config['output'].get('serverName'):
        if app_config['output']['use_https']:
            protocol = 'https'
        else:
            protocol = 'http'
        baseurl = f"{protocol}://{app_config['output'].get('serverName')}/i/"
        if dir_name:
            baseurl += dir_name + '/'
    else:
        baseurl = ''

    return baseurl

def trigger_emergency_encoding(input_filepath, output_dir, manifest_path):
    """
    Spawns a detached FFmpeg process to generate a live, appendable HLS stream.
    this is because we did not find a ffmpeg encoded video file, so there is nothing for 
    bento4 to work with. 
    Waits for the first segment to appear before returning.

    This is a failsafe.  It's preferred that files be provided pre-transcoded for ABR support.
    But if casterpak discovers there is only one file, it will attempt to transcode it on the fly.

    If you're reading this, you're probably spending too much money and it's time to optomize your video library
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # We must match Bento4's exact naming convention from media_manifest_base.py
    segment_template = os.path.join(output_dir, "segment-%d.ts")
    first_segment_path = os.path.join(output_dir, "segment-0.ts")

    cmd = [
        "ffmpeg", "-y", "-i", input_filepath,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28", "-vf", "scale=-2:480",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "0", 
        "-hls_playlist_type", "event", 
        "-hls_segment_filename", segment_template,
        manifest_path
    ]

    current_app.logger.info(f"Spawning Emergency JIT Transcode for {input_filepath}")
    
    # Popen detaches the process. stdout/stderr to DEVNULL keeps Docker logs clean.
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Polling Loop
    timeout = 5.0 
    start_time = time.time()
    
    while True:
        if os.path.exists(first_segment_path):
            current_app.logger.info("First JIT segment detected! Releasing request to Nginx.")
            return True
            
        if time.time() - start_time > timeout:
            current_app.logger.error("JIT Transcoding timed out.")
            process.kill() 
            raise EncodingError("JIT Transcoding failed to start in time.")
            
        time.sleep(0.1) 


@bp.route('/i/<path:dir_name>')
def mp4_file(dir_name: t.Union[os.PathLike, str]):
    """Path directly to MP4 file, without a stream"""
    current_app.logger.debug(f"caught 404 for {dir_name}")
    abort(404)


@bp.route('/i/<path:dir_name>/master.m3u8')
def single_bitrate_manifest(dir_name: str):
    """ creates a variant manifest containing a single bitrate file """

    (dirname, filename) = os.path.split(dir_name)

    #sanitize
    filename = filenameRE.sub('', filename)
    dirname = dirnameRE.sub('', dirname)

    ## TEST ME (os.path.join was replaced with 'safe_join')
    files = [safe_join(dirname, filename), ]

    ## TODO: is 'dirname' safe - it's not 'safe joined' and comes directly from the URL
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


@bp.route('/i/abr/<path:dir_name>/master.m3u8')
def abr_manifest(dir_name: str):
    """
    # This is the expensive endpoint, use with caution
    This endpoint acts as the State Manager. 
    If encodings exist, redirects to CSMIL. 
    If not:
       a. start background ABR transcodes (cpu killer)
       b. starts JIT encode, and returns emergency stream. (sub optimal playback)
    """
    
    #determine output dir for segments    
    (dirname, filename) = os.path.split(dir_name)
    #sanitize
    filename = filenameRE.sub('', filename)

    basename, ext = os.path.splitext(filename)
    
    #determine input directory for origonal video file.
    localdir = current_app.config['filesystem']['videoParentPath']
    video_file = safe_join(localdir, dir_name)

    encoder = EncodingManager(video_file)
    try:
        if encoder.renditions_exist():
            # TIER 2: Encodings are ready. Redirect to stateless CSMIL delivery.
            from vodhls.csmil import CsmilDescriptor
            transcodes_dir = os.path.join(dirname, f"{filename}.transcodes")
            csmil = CsmilDescriptor(transcodes_dir, basename, ext, encoder.bitrates)
            redirect_url = f"/i/{transcodes_dir}/{csmil.csmil_string}.csmil/master.m3u8"

            return redirect(redirect_url, code=302)
        else:
            # TIER 3: Emergency. Start the heavy worker...
            encoder.start_background_encoding()
            
            # ...and start the lightweight JIT emergency stream
            hls_manager = vodhls_media_playlist_factory(dir_name)
            trigger_emergency_encoding(
                input_filepath=hls_manager.source_file, 
                output_dir=hls_manager.output_dir,
                manifest_path=hls_manager.output_manifest_filename
            )
            
            # Return a dynamic Master Manifest pointing to the new JIT stream
            child_url = f"/i/{dir_name}/index_0_av.m3u8"
            
            m3u8_text = (
                "#EXTM3U\n"
                "#EXT-X-STREAM-INF:BANDWIDTH=1000000,RESOLUTION=854x480\n"
                f"{child_url}\n"
            )
            
            return Response(m3u8_text, mimetype='application/vnd.apple.mpegurl')

    except FileNotFoundError:
        return abort(404, description="Original source video at videoParentPath/{dir_name} not found.")
    #except Exception as e:
    #    return abort(504, description=f"Encoding failed: {e}")
    ## FOR NOW - don't catch encoding exceptions, debug them.   

@bp.route('/i/<path:csmil_str>.csmil/master.m3u8')
def csmil_parent_manifest(csmil_str: str):
    """
    creates a variant manifest containing multiple bitrate files. the csmil_str is a string of the form
    dir1/dir2/dir3/file1,bitrate1,file2,bitrate

    This is useful when the renditions are already available, and are in an arbitrary naming format.
    """

    csmil_data = CsmilDescriptor.from_string(csmil_str)

    vodhls_manager = vodhls_master_playlist_factory(csmil_data)

    if not vodhls_manager.manifest_exists():
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
    dir_name = dirnameRE.sub('', dir_name)

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

    filename = filenameRE.sub('', filename)
    filepath = dirnameRE.sub('', filepath)

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

    # Nginx Handoff
    # We return an empty body, but tell Nginx where the file is located internally
    response = make_response("")
    response.headers['Content-Type'] = 'video/MP2T'
    
    # This path must match the internal location block in nginx.conf
    internal_nginx_path = f"/protected_media/{filepath}"
    response.headers['X-Accel-Redirect'] = internal_nginx_path
    
    return response

@bp.route('/d/<path:dir_name>/figure/this/out/media.m3u8')
def dash(dir_name: t.Union[os.PathLike, str]):
    current_app.logger.debug(f"calling dash with {dir_name}")
    raise NotImplementedError

@bp.route('/c/<path:dir_name>/figure/this/out/media.m3u8')
def cmaf(dir_name: t.Union[os.PathLike, str]):
    current_app.logger.debug(f"calling cmaf with {dir_name}")
    raise NotImplementedError
