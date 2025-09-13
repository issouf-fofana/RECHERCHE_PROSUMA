from django.db import models
from apps.configs.models import CompareConfig
from apps.datasets.models import Dataset

class CompareRun(models.Model):
    config = models.ForeignKey(CompareConfig, on_delete=models.PROTECT)
    dataset_web1 = models.ForeignKey(Dataset, related_name="+", on_delete=models.PROTECT)
    dataset_desktop = models.ForeignKey(Dataset, related_name="+", on_delete=models.PROTECT)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="running")
    total_rows = models.PositiveIntegerField(default=0)
    diff_rows = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # si pas déjà présent
    export_csv = models.CharField(max_length=255, blank=True)
    export_xlsx = models.CharField(max_length=255, blank=True)
    title = models.CharField("Titre", max_length=255, blank=True, null=True, default="")
    notes = models.TextField("Notes", blank=True, null=True, default="")
    
    class Meta:
        ordering = ["-created_at", "-id"]
class CompareResult(models.Model):
    run = models.ForeignKey(CompareRun, on_delete=models.CASCADE)
    payload = models.JSONField()  # liste de lignes en écart
