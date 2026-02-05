#!/bin/bash
# run.sh
# kicks off the Gunicorn server to run CasterPak

if [ -f /.dockerenv ]; then
    # In Docker, we use the system-installed gunicorn
    GUNICORN_PATH="gunicorn"
else
    # In Dev, we use the local venv binary
    GUNICORN_PATH="./bin/gunicorn"
fi

echo "Starting CasterPak with Gunicorn..."

# 'exec' ensures Gunicorn handles signals like SIGTERM properly
exec $GUNICORN_PATH --bind 0.0.0.0:5000 \
              --workers 4 \
              --timeout 120 \
              casterpak:app