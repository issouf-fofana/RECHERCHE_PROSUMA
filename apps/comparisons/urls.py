# apps/comparisons/urls.py
from django.urls import path
from . import views

app_name = "comparisons"

urlpatterns = [
    # Lancer une comparaison depuis la session (datasets + config)
    path("run/", views.run_with_session, name="run_with_session"),

    # Listing / tableaux de bord
    path("runs/", views.runs_dashboard, name="runs_dashboard"),
    path("results/<int:run_id>/", views.results, name="results"),
    path("summary/<int:run_id>/", views.summary_orders, name="summary_orders"),
    path("latest/", views.latest_for_category, name="latest_for_category"),

    # Actions (modales)
    path("run/<int:run_id>/edit/", views.run_edit, name="run_edit"),
    path("run/<int:run_id>/delete/", views.run_delete, name="run_delete"),
    path("runs/bulk-delete/", views.run_bulk_delete, name="run_bulk_delete"),
]
