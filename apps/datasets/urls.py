from django.urls import path
from . import views

app_name = "datasets"

urlpatterns = [
    path("upload/", views.upload, name="upload"),
]
