#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE

import applogging
from config import get_config
from cleanup import start_maintenance_loop
from encoding.encoding_process_manager import start_encoding_dispatcher

app_config = get_config()

workers = 3
bind = "unix:/home/casterpak/CasterPak/casterpak.sock"

wsgi_app = "app:app"
umask = 0x007  #Gunicorn creates files that are user & group writable.  Not world writable.

debugging = app_config.getboolean('application', 'debug', fallback=False)

loglevel = 'debug' if debugging else 'info'

# Gunicorn owns every log destination. '-' means stdout. Cleanup and
# encoding do not get their own files - they borrow these handlers via
# applogging.use_gunicorn_handlers() in on_starting below.
accesslog = app_config.get('logging', 'access_log', fallback='/var/log/casterpak.access.log')
errorlog = app_config.get('logging', 'error_log', fallback='/var/log/casterpak.error.log')
cleanup_interval = app_config.getint('cache', 'cleanup_interval', fallback=300)

encoding_poll_interval = app_config.getint('encoding', 'poll_interval', fallback=5)
encoding_pool_size = app_config.getint('encoding', 'max_concurrent_encodes', fallback=2)


capture_output = False

# Server hook to initialize the cache cleanup thread.
def on_starting(server):
    """
    This hook runs once in the Gunicorn Master process
    before the worker processes are spawned.
    """
    server.log.info("--------------------------------------------------")
    server.log.info("CASTERPAK: Master Process starting up.")

    # The cleanup and encoding threads run HERE, in the master, so they
    # never see create_app()/setup_gunicorn_logging() - that runs in the
    # workers. Point them at gunicorn's handlers before starting them, or
    # they log into the void.
    applogging.use_gunicorn_handlers(*applogging.CASTERPAK_LOGGERS)

    server.log.info("Cleanup: initializing background maintenance loop.")
    start_maintenance_loop(cleanup_interval,server=server)
    server.log.info("Encoding: initializing background dispatcher loop.")
    start_encoding_dispatcher(poll_interval=encoding_poll_interval,
                               pool_size=encoding_pool_size)
    server.log.info("--------------------------------------------------")