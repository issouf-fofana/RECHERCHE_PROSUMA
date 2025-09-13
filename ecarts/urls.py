# ecarts/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views   # 👈

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.ui.urls")),
    path("datasets/", include("apps.datasets.urls")),
    path("configs/", include("apps.configs.urls")),
    path("comparisons/", include("apps.comparisons.urls")),
    # 👇 indispensable pour 'login', 'logout', etc.
    path("login/",  auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("accounts/", include(("apps.accounts.urls", "accounts"), namespace="accounts")),

] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
