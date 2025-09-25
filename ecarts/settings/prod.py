from .base import *
DEBUG = False
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "example.com").split(",")
ALLOWED_HOSTS=["10.10.9.13","localhost","127.0.0.1"]
# Exemple Postgres :
# DATABASES = {
#   "default": {
#     "ENGINE": "django.db.backends.postgresql",
#     "NAME": os.getenv("POSTGRES_DB","ecarts"),
#     "USER": os.getenv("POSTGRES_USER","ecarts"),
#     "PASSWORD": os.getenv("POSTGRES_PASSWORD",""),
#     "HOST": os.getenv("POSTGRES_HOST","db"),
#     "PORT": os.getenv("POSTGRES_PORT","5432"),
#   }
# }
