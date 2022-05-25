from config import get_config

config = get_config()

level = "INFO"
if config.get('application', 'debug') is True:
    level = "DEBUG"

CASTERPAK_DEFAULT_LOGGING_CONFIG = {
    'version': 1,
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
            'formatter': 'default'
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
