# apps/ui/views.py
import json
import datetime as dt
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Value
from django.db.models.functions import Coalesce
from django.shortcuts import render

from apps.comparisons.models import CompareRun
from apps.catalogs.models import ConfigCategory


# -------------------- Utils --------------------
def _add_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return dt.date(y, m, 1)

def _parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None


# -------------------- Vue dashboard --------------------
@login_required
def home(request):
    user = request.user

    # --- Période ---
    start = _parse_date(request.GET.get("start") or "")
    end = _parse_date(request.GET.get("end") or "")

    if not start and not end:
        end = timezone.now().date()
        start = _add_months(end.replace(day=1), -5)  # 6 derniers mois glissants
    if start and not end:
        end = timezone.now().date()
    if end and not start:
        start = _add_months(end.replace(day=1), -5)

    # --- Catégorie ---
    cat_param = (request.GET.get("category") or "").strip()
    selected_category = ""
    if cat_param and str(cat_param).isdigit():
        selected_category = str(cat_param)
    elif cat_param:
        # On autorise le nom de catégorie dans l'URL
        cat_id = (
            ConfigCategory.objects
            .filter(name__iexact=cat_param)
            .values_list("id", flat=True)
            .first()
        )
        selected_category = str(cat_id) if cat_id else ""

    # --- Magasin (code) ---
    selected_store = (request.GET.get("store") or "").strip()

    # --- Base queryset (période + owner + catégorie) ---
    base_qs = (
        CompareRun.objects
        .select_related("config", "config__category", "dataset_web1", "dataset_desktop")
        .filter(config__owner=user, created_at__date__gte=start, created_at__date__lte=end)
        .order_by("-created_at", "-id")
    )
    if selected_category:
        base_qs = base_qs.filter(config__category_id=selected_category)

    # --- Liste des magasins disponibles (sur période + catégorie, SANS filtre magasin) ---
    stores_qs = (
        CompareRun.objects
        .select_related("dataset_web1", "dataset_desktop")
        .filter(config__owner=user, created_at__date__gte=start, created_at__date__lte=end)
    )
    if selected_category:
        stores_qs = stores_qs.filter(config__category_id=selected_category)

    stores_qs = (
        stores_qs.annotate(
            code=Coalesce("dataset_web1__store_code", "dataset_desktop__store_code"),
            name=Coalesce("dataset_web1__store_name", "dataset_desktop__store_name", Value(""))
        )
        .values("code", "name")
        .exclude(code__isnull=True)
        .exclude(code="")
        .distinct()
        .order_by("code")
    )
    stores = [{"code": s["code"], "name": s["name"]} for s in stores_qs]

    # --- QS final pour KPI/graphes (période + cat + magasin si sélectionné) ---
    runs_qs = base_qs
    if selected_store:
        runs_qs = runs_qs.filter(
            Q(dataset_web1__store_code=selected_store) | Q(dataset_desktop__store_code=selected_store)
        )

    # --- KPI globaux ---
    kpis = {
        "total": runs_qs.count(),
        "success": runs_qs.filter(status="success").count(),
        "failed": runs_qs.filter(status="failed").count(),
        "diffs": runs_qs.aggregate(s=Sum("diff_rows"))["s"] or 0,
    }

    # --- Mini KPI par catégorie (impactés par période ET magasin si sélectionné) ---
    cats = list(ConfigCategory.objects.all().order_by("name"))
    cat_summary = []
    for c in cats:
        c_qs = (
            CompareRun.objects
            .filter(config__owner=user, config__category=c,
                    created_at__date__gte=start, created_at__date__lte=end)
        )
        if selected_store:
            c_qs = c_qs.filter(
                Q(dataset_web1__store_code=selected_store) | Q(dataset_desktop__store_code=selected_store)
            )
        cat_summary.append({
            "id": c.id,
            "name": c.name,
            "runs": c_qs.count(),
            "success": c_qs.filter(status="success").count(),
            "failed": c_qs.filter(status="failed").count(),
            "diffs": c_qs.aggregate(s=Sum("diff_rows"))["s"] or 0,
            "integrated_runs": c_qs.filter(status="success", diff_rows=0).count(),
        })

    # --- Tendance mensuelle (max 12 mois) ---
    first_month = start.replace(day=1)
    last_month = end.replace(day=1)
    months = []
    cur = first_month
    while cur <= last_month and len(months) < 12:
        months.append(cur)
        cur = _add_months(cur, 1)

    labels, runs_series, diffs_series = [], [], []
    for m0 in months:
        m1 = _add_months(m0, 1)
        labels.append(m0.strftime("%b %Y"))
        m_qs = runs_qs.filter(created_at__date__gte=m0, created_at__date__lt=m1)
        runs_series.append(m_qs.count())
        diffs_series.append(m_qs.aggregate(s=Sum("diff_rows"))["s"] or 0)

    # --- Donut par statut ---
    status_counts = {
        "running": runs_qs.filter(status="running").count(),
        "success": runs_qs.filter(status="success").count(),
        "failed": runs_qs.filter(status="failed").count(),
    }

    # --- Dernières vérifications ---
    recent_runs = list(runs_qs[:4])

    ctx = {
        "start": start, "end": end,
        "selected_category": selected_category,
        "selected_store": selected_store,

        "categories": cats,
        "stores": stores,
        "cat_summary": cat_summary,

        "kpis": kpis,
        "labels_json": json.dumps(labels),
        "runs_series_json": json.dumps(runs_series),
        "diffs_series_json": json.dumps(diffs_series),
        "status_labels_json": json.dumps(list(status_counts.keys())),
        "status_values_json": json.dumps(list(status_counts.values())),
        "has_line_data": any(runs_series) or any(diffs_series),
        "has_donut_data": sum(status_counts.values()) > 0,

        "recent_runs": recent_runs,
    }
    return render(request, "dashboards/home.html", ctx)
