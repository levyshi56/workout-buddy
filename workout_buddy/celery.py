import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workout_buddy.settings")

app = Celery("workout_buddy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.task_always_eager = False
app.conf.imports = ("tasks.rest_timer",)

import tasks.rest_timer  # noqa: E402, F401 — force registration on Railway
