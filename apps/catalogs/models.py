from django.db import models
class ConfigCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)  # Commande, Facture, BR...
    description = models.TextField(blank=True)
    def __str__(self): return self.name

class Store(models.Model):
    code = models.CharField(max_length=10, unique=True)   # ex: "230"
    name = models.CharField(max_length=100)               # ex: "CASINO PRIMA"
    def __str__(self): return f"{self.code} — {self.name}"