web: gunicorn workout_buddy.wsgi --log-file -
worker: C_FORCE_ROOT=1 celery -A workout_buddy worker --loglevel=info
