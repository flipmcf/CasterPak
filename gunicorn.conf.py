
from config import get_config
from cleanup import start_maintenance_loop

app_config = get_config()

workers = 3
bind = "unix:/home/casterpak/CasterPak/casterpak.sock"

wsgi_app = "app:app"
umask = 0x007  #Gunicorn creates files that are user & group writable.  Not world writable.

loglevel = 'debug'

accesslog = app_config.get('logging', 'access_log', fallback='/var/log/casterpak.access.log')
errorlog = app_config.get('logging', 'error_log', fallback='/var/log/casterpak.error.log')
cachelog = app_config.get('logging', 'cache_log', fallback='/var/log/casterpak.cache.log')
cleanup_interval = app_config.getint('cache', 'cleanup_interval', fallback=300)


capture_output = False

# Server hook to initialize the cache cleanup thread.
def on_starting(server):
    """
    This hook runs once in the Gunicorn Master process 
    before the worker processes are spawned.
    """
    server.log.info("--------------------------------------------------")
    server.log.info("CASTERPAK: Master Process starting up.")
    server.log.info("Cleanup: initializing background maintenance loop.")
    start_maintenance_loop(cleanup_interval,server=server)
    server.log.info("--------------------------------------------------")