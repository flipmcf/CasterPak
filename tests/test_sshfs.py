#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#BSD 3-Clause License
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
import hashlib
import os
import random
import argparse

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
ch = logging.StreamHandler()
logger.addHandler(ch)


sshfs_drive = "/mnt/netstorage"
common_path = "/143604/kaltura"
identity_file=""
temp_destination = '.'

def run_test(dirlist, args):
    hashalgo = hashlib.md5
    logger.debug(f'reading {sshfs_drive}{common_path}')

    sshfs_filename = get_rand_file(f"{sshfs_drive}{common_path}", prepaths=dirlist)

    logger.debug(f'hashing {sshfs_filename}')
    sshfs_hash = hash(sshfs_filename, chunk_size=65536, algo=hashalgo)

    remote_filename = os.path.relpath(sshfs_filename, sshfs_drive)

    logger.debug(f'copying {remote_filename} to {temp_destination}')
    copied_filename = copy_file(remote_filename, temp_destination)

    logger.debug(f'hashing {copied_filename}')
    copied_hash = hash(copied_filename, chunk_size=65536, algo=hashalgo)

    logger.info(f"{sshfs_hash} == {copied_hash}")
    if sshfs_hash == copied_hash:
        logger.info(f"{remote_filename} Passed")
        retval = 0
    else:
        logger.error(f"{remote_filename} Error")
        logger.error(f"{sshfs_hash}   {sshfs_filename}")
        logger.error(f"{copied_hash}   {copied_filename}")
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


def hash(filename, chunk_size=8192, algo=None):
    if algo is None:
        algo = hashlib.blake2b

    with open(filename, "rb") as f:
        file_hash = algo()
        while chunk := f.read(chunk_size):
            file_hash.update(chunk)

    return file_hash.hexdigest()


def copy_file(filename, dest):

    scp_command = f"scp -oHostKeyAlgorithms=+ssh-dss -i {identity_file} sshacs@rfa.scp.upload.akamai.com:{filename} {dest}"
    logger.debug(scp_command)
    os.system(scp_command)
    return os.path.join(dest, os.path.basename(filename))


def cleanup(filename, dest):
    os.remove(dest+'/'+filename)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--debug', action="store_true")
    parser.add_argument('--dirlist')
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if not args.dirlist:
        logger.debug(f"reading {sshfs_drive}{common_path} to pre-determine paths to try")
        dirlist = os.listdir(f"{sshfs_drive}{common_path}")
    else:
        logger.debug(f"reading {args.dirlist}")
        with open(args.dirlist) as f:
            dirlist = [line.strip() for line in f.readlines() if line]

    logger.debug("debug enabled")
    while True:
        run_test(dirlist, args)
