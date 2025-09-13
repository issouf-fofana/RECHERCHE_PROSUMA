from django.db import models
from django.conf import settings
from apps.catalogs.models import ConfigCategory
from pathlib import Path

class FileSource(models.TextChoices):
    WEB1 = "web1", "Site Web 1"
    DESKTOP = "desktop", "App Desktop"

def dataset_upload_path(instance, filename):
    return f"datasets/{instance.owner_id}/{instance.source}/{filename}"

class Dataset(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    source = models.CharField(max_length=20, choices=FileSource.choices)
    category = models.ForeignKey(ConfigCategory, on_delete=models.PROTECT)
    file = models.FileField(upload_to=dataset_upload_path)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    rows = models.PositiveIntegerField(default=0)
    columns = models.PositiveIntegerField(default=0)
    header = models.JSONField(default=list)
    
    store_code = models.CharField(max_length=10, blank=True, null=True)
    store_name = models.CharField(max_length=100, blank=True, null=True)

    def filename(self) -> str:
        return Path(self.file.name).name

  

    def __str__(self):
        return f"{self.owner} - {self.source} - {self.file.name}"
