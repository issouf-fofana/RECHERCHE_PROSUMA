# ecarts/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.ui.urls")),
    path("datasets/", include("apps.datasets.urls")),
    path("configs/", include("apps.configs.urls")),
    path("comparisons/", include("apps.comparisons.urls")),

    # 👇 indispensable pour 'login', 'logout', etc.
    path("accounts/", include("django.contrib.auth.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
