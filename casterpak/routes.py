import os
import re
import typing as t

from flask import Blueprint, abort, current_app, send_from_directory, send_file
from werkzeug.utils import safe_join

import cachedb
from vodhls import EncodingError
from vodhls.factory import (vodhls_master_playlist_factory,
                            vodhls_media_playlist_factory)

from encoding import EncodingManager

# valid characters in a filename
filenameRE = re.compile(r'[^.a-zA-Z\d_-]')
# valid characters in a directory path:
dirnameRE = re.compile(r'[^.a-zA-Z\d_/-]')

bp = Blueprint('casterpak', __name__)


def get_base_url(dir_name: t.Union[os.PathLike, str]) -> str:
    app_config = current_app.config
    if app_config['output'].get('serverName'):
        if app_config['output'].getboolean('use_https', fallback=False):
            protocol = 'https'
        else:
            protocol = 'http'
        baseurl = f"{protocol}://{app_config['output'].get('serverName')}/i/{dir_name}/"
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
    This endpoint will spin up encoding jobs for renditions.
    """
    
    #determine output dir for segments    
    (dirname, filename) = os.path.split(dir_name)
    #sanitize
    filename = filenameRE.sub('', filename)
    output_dirname = dirnameRE.sub('', dirname)
    
    #determine input directory for origonal video file.
    localdir = current_app.config['filesystem']['videoParentPath']
    video_file = safe_join(localdir, dir_name)


    # This is where we decide IF we create renditions.
    # It checks the .transcodes folder and handles the FFmpeg logic.
    encoder = EncodingManager(video_file)

    try:
        rendition_paths = encoder.get_renditions()
    except FileNotFoundError:
        return abort(404, description="Original source video at videoParentPath/{dir_name} not found.")
    #except Exception as e:
    #    return abort(504, description=f"Encoding failed: {e}")
    ## FOR NOW - don't catch encoding exceptions, debug them.
    
    vodhls_manager = vodhls_master_playlist_factory(rendition_paths, output_dirname)

    #the input file cache should be updated with the new renditions.
    if not vodhls_manager.manifest_exists():
        vodhls_manager.set_baseurl(get_base_url(dir))   
   
    # Create or verify the rendition for each bitrate
    try:
        vodhls_manager.output_hls()
    except FileNotFoundError:
        abort(404)

    #the segment files 
    for manager in vodhls_manager.segment_managers:
        if manager['status'] != 'ready':
            continue
        segment_dir_name = manager['segment_manager'].filename
        db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
        db.addrecord(filename=segment_dir_name)

    return send_from_directory(directory=vodhls_manager.output_dir,
                               path=vodhls_manager.master_playlist_name,
                               mimetype="application/vnd.apple.mpegurl")

@bp.route('/i/<path:csmil_str>.csmil/master.m3u8')
def csmil_parent_manifest(csmil_str: str):
    """
    creates a variant manifest containing multiple bitrate files. the csmil_str is a string of the form
    dir1/dir2/dir3/file1,bitrate1,file2,bitrate

    This is useful when the renditions are already available, and are in an arbitrary naming format.
    """

    csmil_chunks = csmil_str.split('/')
    dirs = csmil_chunks[:-1]
    files = csmil_chunks[-1]
    file_chunks = files.split(',')

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

    if not hls_manager.segment_exists(filename):
        current_app.logger.info(f"request for segment {filepath} that does not exist. creating manifest")

        hls_manager.set_baseurl(get_base_url(dir_name))
        try:
            hls_manager.create()
        except EncodingError:
            abort(500)

    db = cachedb.CacheDB(cache_name=cachedb.SEGMENT_FILE_CACHE)
    db.addrecord(filename=dir_name)

    return send_from_directory(directory=current_app.config['output']['segmentParentPath'],
                               path=filepath,
                               mimetype="video/MP2T"
                               )


@bp.route('/i/<path:dir_name>/figure/this/out/media.m3u8')
def dash(dir_name: t.Union[os.PathLike, str]):
    current_app.logger.debug(f"calling dash with {dir_name}")
    raise NotImplementedError
