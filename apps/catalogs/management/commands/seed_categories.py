from django.core.management.base import BaseCommand
from apps.catalogs.models import ConfigCategory

class Command(BaseCommand):
    help = "Seed default categories"
    def handle(self, *args, **options):
        for name in ["Commande","Facture","BR"]:
            obj, created = ConfigCategory.objects.get_or_create(name=name)
            self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Exists'}: {obj.name}"))
