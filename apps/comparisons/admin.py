from django.contrib import admin
from .models import CompareRun, CompareResult

@admin.register(CompareRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ("id","config","status","diff_rows","started_at","finished_at")

@admin.register(CompareResult)
class ResultAdmin(admin.ModelAdmin):
    list_display = ("run",)
