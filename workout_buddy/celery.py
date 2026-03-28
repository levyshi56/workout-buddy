import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workout_buddy.settings")

app = Celery("workout_buddy")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["tasks"])
