#!/bin/bash
# run.sh
# kicks off the Gunicorn server to run CasterPak


echo "Starting CasterPak with Gunicorn..."

# 'exec' ensures Gunicorn handles signals like SIGTERM properly
exec gunicorn --bind 0.0.0.0:5000 \
              --workers 4 \
              --timeout 120 \
              casterpak:app