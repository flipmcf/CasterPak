import typing as t
import os

from config import config
from bento4.mp4utils import Mp42Hls

import logging
logger = logging.getLogger('vodhls')

class Options_Config(object):
    def __init__(self, config):
        self.base_config = config

    def __getattr__(self, item):
        return self.base_config[item]


def validate_path(path):
    actualPath = '/'.join((config['videoParentPath'], path))

    try:
        statinfo = os.stat(actualPath)
    except FileNotFoundError:
        logger.debug(f"404 for {actualPath} not a valid path")
        return False
    return True


def manifest_exists(path: t.Union[os.PathLike, str]) -> bool:
    childManifestPath = config['segmentParentPath']+path

    try:
        statinfo = os.stat(childManifestPath)
    except FileNotFoundError:
        return False
    return True


def create_manifest_and_segments(path: t.Union[os.PathLike, str]) -> bool:
    input_file: os.PathLike = '/'.join((config['videoParentPath'], path))
    output_dir: os.PathLike = '/'.join((config['segmentParentPath'], path))
    hls_config = {
            'exec_dir': "/home/mcfaddenm/Bento4/bin",
            'debug': True,
            'verbose': False,
            'output_dir': output_dir,
            }

    options = Options_Config(hls_config)
    Mp42Hls(options, input_file)

