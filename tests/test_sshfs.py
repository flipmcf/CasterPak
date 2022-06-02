import hashlib
import os
import random

""" Let's work sshfs and really see if it's fixed

1) find a random file on a sshfs filesystem
2) md5 that file - save the hash
3) copy that same file (scp) to a temp directory
4) md5 the copied file.
5) compare the hashes
6) if the hashes don't match, fail.
7) Repeat until user is satisfied.


"""

import logging

logger = logging.getLogger('test_sshfs')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
logger.addHandler(ch)

# logger.debug("debug enabled")

sshfs_drive = "/mnt/netstorage"
common_path = "/143604/kaltura"
identity_file="/home/mcfaddenm/.ssh/netstorage"
temp_destination = '.'

def run_test(rootdir_cache):
    logger.debug(f'reading {sshfs_drive}{common_path}')
    sshfs_filename = get_rand_file(f"{sshfs_drive}{common_path}", prepaths=rootdir_cache)

    logger.debug(f'hashing {sshfs_filename}')
    sshfs_hash = hash(sshfs_filename)

    remote_filename = os.path.relpath(sshfs_filename, sshfs_drive)

    copied_filename = copy_file(remote_filename, temp_destination)
    copied_hash = hash(copied_filename)

    if sshfs_hash == copied_hash:
        print(f"{remote_filename} Passed")
        retval = 0
    else:
        print(f"{remote_filename} Error")
        retval = 1

    cleanup(copied_filename, temp_destination)

    return retval


def get_rand_file(parent, prepaths=None):

    if prepaths is not None:
        dirlist = prepaths
    else:
        dirlist = os.listdir(parent)

    elem = random.choice(dirlist)

    rand_path = parent+'/'+elem
    logger.debug(f"picked {rand_path}")
    if os.path.isfile(rand_path):
        logger.debug(f"returning {rand_path}")
        return rand_path
    else:
        logger.debug(f"traversing {rand_path}")
        return get_rand_file(rand_path)


def hash(filename):
    with open(filename, "rb") as f:
        file_hash = hashlib.blake2b()
        while chunk := f.read(8192):
            file_hash.update(chunk)

    return file_hash.hexdigest()


def copy_file(filename, dest):

    scp_command = f"scp -oHostKeyAlgorithms=+ssh-dss -i {identity_file} sshacs@rfa.scp.upload.akamai.com:{filename} {dest}"
    os.system(scp_command)
    return os.path.join(dest, os.path.basename(filename))


def cleanup(filename, dest):
    os.remove(dest+'/'+filename)


if __name__ == "__main__":
    rootdir_cache = os.listdir(f"{sshfs_drive}{common_path}")
    while True:
        run_test(rootdir_cache)
