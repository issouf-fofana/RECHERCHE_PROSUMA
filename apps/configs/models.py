from django.db import models
from django.conf import settings
from apps.catalogs.models import ConfigCategory

class CompareConfig(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category = models.ForeignKey(ConfigCategory, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)

    columns_web1 = models.JSONField(default=list)
    columns_desktop = models.JSONField(default=list)

    # ⬇️ AVANT: CharField ; MAINTENANT: listes ordonnées
    join_key_web1 = models.JSONField(default=list)     # ex: ["Ref", "Date"]
    join_key_desktop = models.JSONField(default=list)  # ex: ["NCDE", "DATE"]
    join_type = models.CharField(max_length=10, default="outer")
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("owner", "category", "name")

    def __str__(self):
        return f"{self.name} ({self.category})"
