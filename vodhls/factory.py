#Copyright (c) 2026, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import logging
import typing as t
import os

from config import get_config

logger = logging.getLogger('vodhls')


def vodhls_master_playlist_factory(csmil_descriptor):
    """
    :param csmil_descriptor: a CsmilDescriptor. This is all the manager is given:
        the segment cache root comes from config, and everything beneath it
        (output directory, master playlist name, renditions) is derived from the
        descriptor.
    :return: an instance of a Multivariant 'master' HLS manager
    """
    from vodhls.master_manifest import MultivariantManager

    return MultivariantManager(csmil_descriptor)


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
    elif input_type.lower() == 's3':
        from vodhls.media_manifest_s3 import MediaManager_s3
        return MediaManager_s3(filename)
    elif input_type == 'ftp':
        # return MediaManager_ftp(filename)
        raise NotImplementedError(f'{input_type} not implemented')
    else:
        raise ValueError(f'unknown input_type {input_type}')
