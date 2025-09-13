from django.urls import path
from . import views

app_name = "configs"

urlpatterns = [
    path("choose-columns/", views.choose_columns, name="choose_columns"),
]
