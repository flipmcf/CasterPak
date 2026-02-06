
from config import get_config

app_config = get_config()

workers = 3
bind = "unix:/home/casterpak/CasterPak/casterpak.sock"

wsgi_app = "app:app"
umask = 0x007  #Gunicorn creates files that are user & group writable.  Not world writable.

loglevel = 'debug'

accesslog = app_config.get('logging', 'access_log', fallback='/var/log/casterpak.access.log')
errorlog = app_config.get('logging', 'error_log', fallback='/var/log/casterpak.error.log')
cachelog = app_config.get('logging', 'cache_log', fallback='/var/log/casterpak.cache.log')


capture_output = False

# Server hook to initialize the cache cleanup thread.
def on_starting(server):
    # TODO create a thread to run the cleanup function
    pass