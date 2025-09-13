from django.db import models
from django.conf import settings

class Profile(models.Model):
    ADMIN = "admin"
    USER = "user"
    ROLE_CHOICES = [(ADMIN, "Admin"), (USER, "User")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=USER)

    def is_admin(self) -> bool:
        return self.role == self.ADMIN

    def __str__(self):
        return f"{self.user} ({self.role})"
