import os

from config import config


def validate_path(path):
    actualPath = config['videoParentPath']+path

    try:
        statinfo = os.stat(actualPath)
    except FileNotFoundError:
        return False
    return True

def manifest_exists(path):
    childManifestPath = config['segmentParentPath']+path

    try:
        statinfo = os.stat(childManifestPath)
    except FileNotFoundError:
        return False
    return True


def create_manifest_and_segments(path):
    return False