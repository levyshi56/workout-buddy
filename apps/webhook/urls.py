from django.urls import path
from . import views

urlpatterns = [
    path("webhook/linq/", views.linq_webhook, name="linq_webhook"),
    path("health/", views.health_check, name="health_check"),
]
