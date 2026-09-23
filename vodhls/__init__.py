#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
class EncodingError(Exception):
    """ this error says something in the encoding binaries went wrong
    """
    pass


class ConfigurationError(Exception):
    pass


class InputFetchError(Exception):
    """ an input backend (S3, http, ...) could not deliver a file that is
    not simply missing - bad credentials, network failure, etc. Distinct
    from FileNotFoundError on purpose: a missing video is a 404, a broken
    backend is not.
    """
    pass
