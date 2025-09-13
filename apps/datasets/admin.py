from django.contrib import admin
from .models import Dataset
@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("owner","source","category","uploaded_at","rows","columns")
