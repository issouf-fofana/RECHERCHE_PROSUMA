from django.contrib import admin
from .models import CompareConfig
@admin.register(CompareConfig)
class CompareConfigAdmin(admin.ModelAdmin):
    list_display = ("name","owner","category","is_active","join_type")
    list_filter = ("category","is_active")
