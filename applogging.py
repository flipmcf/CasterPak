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
    },
    'handlers': {
        'wsgi': {
            'class': 'logging.StreamHandler',
            'stream': 'ext://flask.logging.wsgi_errors_stream',
            'formatter': 'default'
            },
    },
    'root': {
        'level': level,
        'handlers': ['wsgi']
    },
}


#: Every CasterPak logger that is not the Flask app logger. These are the
#: ones that have to be re-pointed at gunicorn, because nothing else
#: attaches a handler to them.
CASTERPAK_LOGGERS = ('vodhls', 'CasterPak-cleanup', 'CasterPak-encoding')

#: Short, grep-able tag for each of the above - see TagFilter.
CASTERPAK_LOGGER_TAGS = {
    'vodhls': 'vodhls',
    'CasterPak-cleanup': 'cleanup',
    'CasterPak-encoding': 'encoding',
}


class TagFilter(logging.Filter):
    """Prepends '[tag] ' to every record from a logger - the only way this
    project distinguishes its own subsystems in gunicorn's shared, unified
    output. Cheap and grep-friendly by design (see CASTERPAK_LOGGER_TAGS'
    docstring) - downstream tools like grep or syslog are expected to do the
    rest."""

    def __init__(self, tag: str):
        super().__init__()
        self.tag = tag

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = f"[{self.tag}] {record.msg}"
        return True


def _install_tag_filters() -> None:
    """Runs once, at import time - see the module-level call below. Not
    inside use_gunicorn_handlers: a Filter only needs adding once per
    process, and Python only executes a module's top-level code once no
    matter how many times it's imported, so this is naturally idempotent
    without needing its own guard."""
    for name, tag in CASTERPAK_LOGGER_TAGS.items():
        logging.getLogger(name).addFilter(TagFilter(tag))


_install_tag_filters()


def use_gunicorn_handlers(*logger_names: str) -> None:
    """Point the named loggers at gunicorn's handlers.

    This is the single rule for log destinations in CasterPak: a logger
    never opens its own file. Gunicorn owns where logs go (accesslog /
    errorlog, where '-' means stdout), and every CasterPak logger borrows
    its handlers.

    Needs calling in both gunicorn processes, because they are different
    processes and handlers do not survive the fork in any useful sense:

    * the WORKER, from create_app() - app.logger and the request-path
      loggers.
    * the MASTER, from gunicorn.conf.py's on_starting hook - the cleanup
      and encoding background threads start there, before workers exist.

    Outside gunicorn (tests, a bare `flask run`, or a component run directly
    for debugging) 'gunicorn.error' has no handlers, so this is a no-op and
    the caller's own basic config stands. There is no other supported way to
    run this in production - CasterPak is container-only, and gunicorn's
    master process is what schedules cleanup and encoding, not cron.
    """
    gunicorn_logger = logging.getLogger('gunicorn.error')
    if not gunicorn_logger.handlers:
        return

    for name in logger_names:
        logger = logging.getLogger(name)
        logger.handlers = gunicorn_logger.handlers
        logger.setLevel(gunicorn_logger.level)
        logger.propagate = False