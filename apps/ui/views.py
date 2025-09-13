# apps/ui/views.py
import json
import datetime as dt
from collections import defaultdict

from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import render

from apps.comparisons.models import CompareRun
from apps.catalogs.models import ConfigCategory
from django.contrib.auth import get_user_model
# apps/ui/views.py
from datetime import date, timedelta
from django.db.models import Q, Sum
from django.utils.dateparse import parse_date





User = get_user_model()


def _add_months(d: dt.date, months: int) -> dt.date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return dt.date(y, m, 1)


def _parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except Exception:
        return None




def _d(dflt=None, s=None):
    """parse_date avec valeurs par défaut raisonnables"""
    if s:
        dt = parse_date(s)
        if dt:
            return dt
    return dflt


@login_required
def home(request):
    # ---- Période
    today = timezone.localdate()
    start = _d(today - timedelta(days=180), request.GET.get("start"))
    end   = _d(today, request.GET.get("end"))

    # ---- Filtres
    cat_id      = (request.GET.get("category") or "").strip()
    store_code  = (request.GET.get("store") or "").strip()

    # Si admin: on peut choisir "owner"; sinon forcé à l'utilisateur courant.
    selected_owner = None
    if request.user.is_staff:
        selected_owner = (request.GET.get("owner") or "").strip() or None
    else:
        selected_owner = str(request.user.id)

    # ---- Base queryset
    qs = (CompareRun.objects
          .select_related("config", "config__category", "dataset_web1", "dataset_desktop", "config__owner")
          .filter(created_at__date__gte=start, created_at__date__lte=end)
          .order_by("-created_at", "-id"))

    # Propriété: owner
    if selected_owner:
        qs = qs.filter(config__owner_id=selected_owner)

    # Catégorie
    if cat_id:
        qs = qs.filter(config__category_id=cat_id)

    # Magasin (web1 ou desktop)
    if store_code:
        qs = qs.filter(Q(dataset_web1__store_code=store_code) | Q(dataset_desktop__store_code=store_code))

    # ---- KPI globaux
    kpis = {
        "total":   qs.count(),
        "success": qs.filter(status="success").count(),
        "failed":  qs.filter(status="failed").count(),
        "diffs":   qs.aggregate(s=Sum("diff_rows"))["s"] or 0,
    }

    # ---- Listes filtres
    categories = ConfigCategory.objects.all().order_by("name")

    # Stores disponibles (dédupliqués) dans le périmètre filtré
    stores_seen = set()
    stores = []
    for r in qs[:1000]:
        for ds in (r.dataset_web1, r.dataset_desktop):
            if not ds:
                continue
            code = (ds.store_code or "").strip()
            name = (ds.store_name or "").strip()
            if not code and not name:
                continue
            key = (code, name)
            if key in stores_seen:
                continue
            stores_seen.add(key)
            stores.append({"code": code, "name": name})
    stores.sort(key=lambda x: (x["code"] or "", x["name"] or ""))

    # ---- Résumés par catégorie (cartes)
    cat_summary = []
    for c in categories:
        sub = qs.filter(config__category=c)
        runs = sub.count()
        cat_summary.append({
            "id": c.id,
            "name": c.name,
            "runs": runs,
            "success": sub.filter(status="success").count(),
            "failed": sub.filter(status="failed").count(),
            "diffs": sub.aggregate(s=Sum("diff_rows"))["s"] or 0,
            "integrated_runs": sub.filter(status="success", diff_rows=0).count(),
        })

    # ---- Résumés par magasin (cartes)
    per_store_map = defaultdict(lambda: {"code": "", "name": "", "runs": 0, "success": 0, "failed": 0, "diffs": 0})
    for r in qs:
        ds = r.dataset_web1 or r.dataset_desktop
        code = (getattr(ds, "store_code", "") or "").strip()
        name = (getattr(ds, "store_name", "") or "").strip()
        if not code and not name:
            # range les runs "sans magasin" sous une clé vide si besoin
            code = ""
        slot = per_store_map[code]
        slot["code"] = code
        slot["name"] = name or slot["name"]
        slot["runs"] += 1
        if r.status == "success":
            slot["success"] += 1
        elif r.status == "failed":
            slot["failed"] += 1
        slot["diffs"] += (r.diff_rows or 0)
    per_store = list(per_store_map.values())
    per_store.sort(key=lambda x: (x["code"] or "~~~~", x["name"] or ""))  # les codes vides à la fin

    # ---- Graphiques (simple agrégat mensuel)
    months = []
    per_month_runs = defaultdict(int)
    per_month_diffs = defaultdict(int)
    for r in qs:
        key = r.created_at.strftime("%Y-%m")
        months.append(key)
        per_month_runs[key] += 1
        per_month_diffs[key] += (r.diff_rows or 0)
    labels = sorted(set(months))
    runs_series = [per_month_runs[m] for m in labels]
    diffs_series = [per_month_diffs[m] for m in labels]

    status_labels = ["running", "success", "failed"]
    status_values = [qs.filter(status=s).count() for s in status_labels]

    # ---- Derniers runs
    recent_runs = list(qs[:10])

    # ---- Propriétaires (pour le select “Utilisateur”) si admin
    User = get_user_model()
    owners = list(User.objects.order_by("username").values("id", "username")) if request.user.is_staff else []

    ctx = {
        "start": start, "end": end,
        "categories": categories,
        "stores": stores,
        "kpis": kpis,
        "cat_summary": cat_summary,
        "per_store": per_store if stores else [],
        "recent_runs": recent_runs,

        # Graphs
        "labels_json": labels,
        "runs_series_json": runs_series,
        "diffs_series_json": diffs_series,
        "has_line_data": bool(labels),
        "status_labels_json": status_labels,
        "status_values_json": status_values,
        "has_donut_data": any(status_values),

        # Sélections
        "selected_category": cat_id,
        "selected_store": store_code,
        "selected_owner": str(selected_owner) if selected_owner else "",

        # Pour le sélecteur d'admin
        "owners": owners,
    }
    return render(request, "dashboards/home.html", ctx)
