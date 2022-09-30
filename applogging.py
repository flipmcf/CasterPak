#Copyright (c) 2022, Michael McFadden & Radio Free Asia
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
from config import get_config

config = get_config()

import logging

level = logging.INFO
if config.getboolean('application', 'debug') is True:
    level = logging.DEBUG

CASTERPAK_DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {'format': '[%(asctime)s] %(levelname)s in %(module)s: %(message)s', },
        'cleanup': {'format': '[%(asctime)s] %(levelname)s CasterPak Cleanup: %(message)s', }
    },
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
            },
        'vodhls': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default',
            },
        'CasterPak-cleanup': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'cleanup'
            },
    },
    'root': {
        'level': level,
        'handlers': ['wsgi']
    },
}

