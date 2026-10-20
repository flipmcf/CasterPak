#Copyright (c) 2026, Michael McFadden
#GNU GENERAL PUBLIC LICENSE Version 2
#See file LICENCE or visit https://github.com/flipmcf/CasterPak/blob/master/LICENSE
"""
Gunicorn settings for the library service:

    gunicorn -c gunicorn.library.conf.py "library:create_app()"

Deliberately NOT gunicorn.conf.py: that file starts CasterPak's cache-cleanup
and encoding threads in the master process, and the library must never run
either. It only accepts uploads and answers API calls.
"""
bind = "0.0.0.0:5001"

# Uploads are slow: a worker is busy for as long as the client takes to send
# the file. Threads let one worker carry several of them at once.
worker_class = "gthread"
workers = 2
threads = 4

# A multi-GB upload over a slow link legitimately takes minutes.
timeout = 900
graceful_timeout = 30

# Log to stdout/stderr; the container runtime collects them.
accesslog = "-"
errorlog = "-"
