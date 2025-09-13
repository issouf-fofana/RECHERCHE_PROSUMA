from django.contrib import admin
from .models import ConfigCategory
@admin.register(ConfigCategory)
class ConfigCategoryAdmin(admin.ModelAdmin):
    list_display = ("name","description")
