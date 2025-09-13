from django.urls import path
from . import views

app_name = "comparisons"

urlpatterns = [
    path("run/", views.run_with_session, name="run_with_session"),
    path("results/<int:run_id>/", views.results, name="results"),
    path("runs/", views.runs_dashboard, name="runs_dashboard"),   # 👈 dashboard

]
