import applogging

workers = 3
bind = "unix:/home/casterpak/CasterPak/casterpak.sock"

wsgi_app = "casterpak:app"
umask = 777  #A bit mask for the file mode on files written by Gunicorn.

loglevel = 'debug'
accesslog = "/var/log/casterpak.access.log"
errorlog = "/var/log/casterpak.error.log"

capture_output = False


wsgi_app = "casterpak:app"
