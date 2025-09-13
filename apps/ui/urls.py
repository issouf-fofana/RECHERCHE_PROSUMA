# apps/ui/urls.py
from django.urls import path
from . import views
from django.urls import include, path

app_name = "ui"

urlpatterns = [
    path("", views.home, name="home"),

    
]
