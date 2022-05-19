import typing as t
import os
import logging
import config
from urllib.parse import urljoin
from bento4.mp4utils import Mp42Hls

logger = logging.getLogger('vodhls')
config = config.get_config()


class OptionsConfig(object):
    """ This is a basic class that turns a dictionary into an object,
        it's job is to impersonate an optparse.OptionParser instance.
        We end up passing an instance of this to Mp42Hls
    """
    def __init__(self, config_dict):
        self.base_config = config_dict

    def __getattr__(self, item):
        return self.base_config[item]


def validate_path(dir_name):
    actual_path: os.PathLike = os.path.join(config['input']['videoParentPath'], dir_name)

    try:
        os.stat(actual_path)
    except FileNotFoundError:
        logger.debug(f"404 for {actual_path} not a valid path")
        return False
    return True


def manifest_exists(dir_name: t.Union[os.PathLike, str]) -> bool:
    child_manifest_path: os.PathLike = os.path.join(config['output']['segmentParentPath'], dir_name)

    try:
        os.stat(child_manifest_path)
    except FileNotFoundError:
        return False
    return True


def segment_exists(dir_name: t.Union[os.PathLike, str]) -> bool:
    segment_path: os.PathLike = os.path.join(config['output']['segmentParentPath'], dir_name)

    try:
        os.stat(segment_path)
    except FileNotFoundError:
        return False
    return True


def create_manifest_and_segments(dir_name: t.Union[os.PathLike, str],
                                 base_url: str) -> bool:
    input_file: os.PathLike = os.path.join(config['input']['videoParentPath'], dir_name)
    output_dir: os.PathLike = os.path.join(config['output']['segmentParentPath'], dir_name)
    hls_config = {
            'exec_dir': config['bento4']['binaryPath'],
            'debug': True,
            'verbose': False,
            }

    kwargs = {
        'index_filename':            os.path.join(output_dir, (config['output']['childManifestFilename'])),
        'segment_filename_template': os.path.join(output_dir, 'segment-%d.ts'),
        'segment_url_template':      urljoin(base_url, 'segment-%d.ts'),
        'show_info':                 True,
        'segment_duration':          "10",
        'allow-cache':               True,
    }

    options = OptionsConfig(hls_config)

    if not os.path.isdir(output_dir):
        make_segment_dir(output_dir)

    try:
        Mp42Hls(options, input_file, **kwargs)
    except Exception:
        logger.exception("Error creating segment files")
        return False

    return True


def make_segment_dir(dir_name: t.Union[os.PathLike, str]) -> None:

    if not os.path.isdir(config['output']['segmentParentPath']):
        # configuration is wrong.  This path should always exist.
        logger.error("The segment directory doesn't exist")
        raise FileNotFoundError

    os.makedirs(os.path.join(config['output']['segmentParentPath'], dir_name))
