import os
from decouple import config

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SECRET_KEY = config("SECRET_KEY", default="dev-secret-key-change-in-production")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*").split(",")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.webhook",
    "apps.conversation",
    "apps.llm",
    "apps.messaging",
    "apps.users",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "workout_buddy.urls"

WSGI_APPLICATION = "workout_buddy.wsgi.application"

# MongoDB via MongoEngine — no Django ORM migrations needed
MONGODB_URI = config("MONGODB_URI", default="mongodb://localhost:27017/workout_buddy")

import mongoengine
mongoengine.connect(db="workout_buddy", host=MONGODB_URI, authentication_source="admin", connect=False)

# Redis / Celery
REDIS_URL = config("REDIS_URL", default="redis://localhost:6379/0")

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
}

# External API keys
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
LINQ_API_KEY = config("LINQ_API_KEY", default="")
LINQ_WEBHOOK_SECRET = config("LINQ_WEBHOOK_SECRET", default="")
LINQ_BASE_URL = config("LINQ_BASE_URL", default="https://api.linqapp.com")
LINQ_FROM_NUMBER = config("LINQ_FROM_NUMBER", default="")

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]
