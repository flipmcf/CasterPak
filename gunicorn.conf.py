
from config import get_config

app_config = get_config()

workers = 3
bind = "unix:/home/casterpak/CasterPak/casterpak.sock"

wsgi_app = "app:app"
umask = 007  #A bit mask for the file mode on files written by Gunicorn.

loglevel = 'debug'

accesslog = app_config.get('logging', 'access_log', fallback='/var/log/casterpak.access.log')
errorlog = app_config.get('logging', 'error_log', fallback='/var/log/casterpak.error.log')

capture_output = False
