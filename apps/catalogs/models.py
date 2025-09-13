from django.db import models
class ConfigCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)  # Commande, Facture, BR...
    description = models.TextField(blank=True)
    def __str__(self): return self.name
