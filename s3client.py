#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
The one place a boto3 S3 client is built from config.ini's [s3] section.

Shared by the streaming side (vodhls/media_manifest_s3.py, which reads) and
the library service (library/storage.py, which writes), so both always talk
to the same bucket the same way. Flat module on purpose, like pathsafety.py.
boto3 is imported lazily: nothing here costs anything unless S3 is in use.
"""
import functools
from configparser import ConfigParser

from vodhls import ConfigurationError


def s3_option(config: ConfigParser, option: str, fallback: str = '') -> str:
    if not config.has_section('s3'):
        raise ConfigurationError("S3 is in use but config.ini has no [s3] section")
    return config.get('s3', option, fallback=fallback).strip()


def bucket_and_prefix(config: ConfigParser):
    """(bucket, prefix) where prefix is normalised: no leading '/', and
    exactly one trailing '/' unless it is empty (bucket root)."""
    bucket = s3_option(config, 'bucket')
    if not bucket:
        raise ConfigurationError("[s3] bucket is not configured")
    prefix = s3_option(config, 'prefix').strip('/')
    return bucket, (prefix + '/' if prefix else '')


def client_from_config(config: ConfigParser):
    return _client_for(
        s3_option(config, 'endpoint_url') or None,
        s3_option(config, 'region') or None,
        s3_option(config, 'access_key_id'),
        s3_option(config, 'secret_access_key'),
        s3_option(config, 'addressing_style', 'auto') or 'auto',
        float(s3_option(config, 'connect_timeout', '5') or 5),
        float(s3_option(config, 'read_timeout', '60') or 60),
        int(s3_option(config, 'max_attempts', '3') or 3),
    )


@functools.lru_cache(maxsize=4)
def _client_for(endpoint_url, region, access_key_id, secret_access_key,
                addressing_style, connect_timeout, read_timeout, max_attempts):
    """One boto3 client per distinct configuration. boto3 clients are
    thread-safe, and creating one is expensive (it loads the service model),
    so it is shared by every request in the worker. Arguments are all
    hashable strings/numbers so this can be an lru_cache."""
    import boto3
    from botocore.config import Config

    kwargs = {}
    if endpoint_url:
        kwargs['endpoint_url'] = endpoint_url
    if region:
        kwargs['region_name'] = region
    # Blank keys mean "use boto3's default credential chain" - env vars,
    # shared credentials, or (on EC2/ECS) the instance/task role. Preferred
    # in production: no secret ever lands in config.ini.
    if access_key_id and secret_access_key:
        kwargs['aws_access_key_id'] = access_key_id
        kwargs['aws_secret_access_key'] = secret_access_key

    return boto3.client(
        's3',
        config=Config(
            signature_version='s3v4',
            s3={'addressing_style': addressing_style},
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            retries={'max_attempts': max_attempts, 'mode': 'standard'},
        ),
        **kwargs,
    )
