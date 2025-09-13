# apps/accounts/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("login/",  auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="ui:home"),              name="logout"),

    # Gestion utilisateurs (staff only)
    path("users/",                         views.users_list,        name="users_list"),
    path("users/create/",                  views.user_create,       name="user_create"),
    path("users/<int:user_id>/edit/",      views.user_edit,         name="user_edit"),
    path("users/<int:user_id>/delete/",    views.user_delete,       name="user_delete"),
    path("users/<int:user_id>/activity/",  views.user_activity,     name="user_activity"),
    path("me/activity/",                   views.my_activity,       name="my_activity"),
    path("users/<int:user_id>/toggle-active/", views.user_toggle_active, name="user_toggle_active"),
]
