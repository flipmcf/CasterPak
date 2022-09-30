#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import logging
import typing as t
import os

from config import get_config

logger = logging.getLogger('vodhls')


def vodhls_master_playlist_factory(files: t.Iterable[t.Union[os.PathLike, str]], output_dir: t.Union[os.PathLike, str]):
    """
    :param files: an iterable with full paths to all input files relative to the configured input directory
    :param output_dir: output directory for segments relative to configured output directory (typically a common dirname of files)
    :return: an instance of a Multivariant 'master' HLS manager
    """
    from vodhls.master_manifest import MultivariantManager
    return MultivariantManager(files, output_dir)


def vodhls_media_playlist_factory(filename):
    """ Factory that returns an instance of an MediaManager depending on configuration
    """
    config = get_config()

    input_type = config['input'].get('input_type', 'filesystem')
    logger.info(f"input type set to {input_type}")

    # TODO - this should be like:
    #  get a manager
    #  attach a input file adapter
    #  return the manager
    #  Stop this pattern or you'll be in multiple inheritance hell.

    if input_type == 'filesystem':
        from vodhls.media_manifest_filesystem import MediaManager_filesystem
        return MediaManager_filesystem(filename)
    elif input_type == 'http':
        from vodhls.media_manifest_http import MediaManager_http
        return MediaManager_http(filename)
    elif input_type == 'ftp':
        # return MediaManager_ftp(filename)
        raise NotImplementedError(f'{input_type} not implemented')
    else:
        raise ValueError(f'unknown input_type {input_type}')
