import typing as t
import os
from os import path

from config import config
from bento4.mp4utils import Mp42Hls

import logging
logger = logging.getLogger('vodhls')


class OptionsConfig(object):
    def __init__(self, config):
        self.base_config = config

    def __getattr__(self, item):
        return self.base_config[item]


def validate_path(dir_name):
    actual_path: os.PathLike = os.path.join(config['videoParentPath'], dir_name)

    try:
        os.stat(actual_path)
    except FileNotFoundError:
        logger.debug(f"404 for {actual_path} not a valid path")
        return False
    return True


def manifest_exists(dir_name: t.Union[os.PathLike, str]) -> bool:
    child_manifest_path: os.PathLike = os.path.join(config['segmentParentPath'], dir_name)

    try:
        os.stat(child_manifest_path)
    except FileNotFoundError:
        return False
    return True


def create_manifest_and_segments(dir_name: t.Union[os.PathLike, str]) -> bool:
    input_file: os.PathLike = os.path.join((config['videoParentPath'], dir_name))
    output_dir: os.PathLike = os.path.join((config['segmentParentPath'], dir_name))
    hls_config = {
            'exec_dir': "/home/mcfaddenm/Bento4/bin",
            'debug': True,
            'verbose': False,
            }

    kwargs = {
        'index_filename':            path.join(output_dir, 'index_0_av.m3u8'),
        'segment_filename_template': path.join(output_dir, 'segment-%d.ts'),
        'segment_url_template':      'segment-%d.ts',
        'show_info':                 True
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

    if not os.path.isdir(config['segmentParentPath']):
        # configuration is wrong.  This path should always exist.
        logger.error("The segment directory doesn't exist")
        raise FileNotFoundError

    os.makedirs(path.join(config['segmentParentPath'], dir_name))





