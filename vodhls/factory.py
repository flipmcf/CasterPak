import logging

from config import get_config

logger = logging.getLogger('vodhls')

def vodhls_media_playlist_factory(filename):
    """ Factory that returns an instance of an VODHLSManager depending on configuration
    """
    config = get_config()

    input_type = config['input'].get('input_type', 'filesystem')
    logger.info(f"input type set to {input_type}")

    if input_type == 'filesystem':
        from vodhls.vodhls_filesystem import VODHLSMediaManager_filesystem
        return VODHLSMediaManager_filesystem(filename)
    elif input_type == 'http':
        from vodhls.vodhls_http import VODHLSMediaManager_http
        return VODHLSMediaManager_http(filename)
    elif input_type == 'ftp':
        # return VODHLSManager_ftp(filename)
        raise NotImplementedError(f'{input_type} not implemented')
    else:
        raise ValueError(f'unknown input_type {input_type}')
