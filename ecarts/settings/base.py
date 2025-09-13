from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = BASE_DIR / "apps"

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
DEBUG = bool(int(os.getenv("DEBUG", "1")))
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "*").split(",")
INSTALLED_APPS = [
    "django.contrib.admin","django.contrib.auth","django.contrib.contenttypes",
    "django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles",
    "crispy_forms","crispy_bootstrap5",
    "apps.accounts","apps.catalogs","apps.datasets","apps.configs","apps.comparisons","apps.audit","apps.ui", "widget_tweaks",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "ecarts.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "apps" / "ui" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.debug",
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ],},
}]

WSGI_APPLICATION = "ecarts.wsgi.application"

# DB simple (SQLite)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Static & media
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "apps" / "ui" / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
WHITENOISE_USE_FINDERS = True

# Crispy
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# === Auth redirections / URLs (namespacées) ===
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "ui:home"
LOGOUT_REDIRECT_URL = "ui:home"
