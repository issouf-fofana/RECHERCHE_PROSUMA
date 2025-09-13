# apps/ui/views.py
import json
import datetime as dt
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import render
from django.utils.dateparse import parse_date

from apps.comparisons.models import CompareRun
from apps.catalogs.models import ConfigCategory


User = get_user_model()


def _display_name(user) -> str | None:
    """Retourne 'Prénom Nom' si dispo, sinon username, sinon None."""
    if not user:
        return None
    try:
        full = (user.get_full_name() or "").strip()
    except Exception:
        full = ""
    return full or getattr(user, "username", None)


def _parse_or(default: dt.date, s: str | None) -> dt.date:
    """parse_date avec valeur par défaut si vide/invalide."""
    if s:
        d = parse_date(s)
        if d:
            return d
    return default


@login_required
def home(request):
    # ---------- Période ----------
    today = timezone.localdate()
    start = _parse_or(today - timedelta(days=180), request.GET.get("start"))
    end   = _parse_or(today, request.GET.get("end"))

    # ---------- Filtres ----------
    cat_id     = (request.GET.get("category") or "").strip()
    store_code = (request.GET.get("store") or "").strip()

    # Admin : peut choisir l'owner. Sinon : forcé à l'utilisateur courant.
    if request.user.is_staff:
        selected_owner = (request.GET.get("owner") or "").strip() or None
    else:
        selected_owner = str(request.user.id)

    # ---------- Base queryset ----------
    qs = (
        CompareRun.objects
        .select_related("config", "config__owner", "config__category",
                        "dataset_web1", "dataset_desktop")
        .filter(created_at__date__gte=start, created_at__date__lte=end)
        .order_by("-created_at", "-id")
    )

    if selected_owner:
        qs = qs.filter(config__owner_id=selected_owner)

    if cat_id:
        qs = qs.filter(config__category_id=cat_id)

    if store_code:
        qs = qs.filter(
            Q(dataset_web1__store_code=store_code) |
            Q(dataset_desktop__store_code=store_code)
        )

    # ---------- KPI globaux ----------
    kpis = {
        "total":   qs.count(),
        "success": qs.filter(status="success").count(),
        "failed":  qs.filter(status="failed").count(),
        "diffs":   qs.aggregate(s=Sum("diff_rows"))["s"] or 0,
    }

    # ---------- Listes pour filtres ----------
    categories = ConfigCategory.objects.all().order_by("name")

    # Magasins déduits du périmètre courant (dédoublés)
    stores_seen: set[tuple[str, str]] = set()
    stores: list[dict] = []
    for r in qs[:1000]:
        for ds in (r.dataset_web1, r.dataset_desktop):
            if not ds:
                continue
            code = (getattr(ds, "store_code", "") or "").strip()
            name = (getattr(ds, "store_name", "") or "").strip()
            if not code and not name:
                continue
            key = (code, name)
            if key in stores_seen:
                continue
            stores_seen.add(key)
            stores.append({"code": code, "name": name})
    stores.sort(key=lambda x: (x["code"] or "", x["name"] or ""))

    # ---------- Résumés par catégorie (cartes) ----------
    cat_summary: list[dict] = []
    for c in categories:
        sub = qs.filter(config__category=c)
        runs = sub.count()
        last_run = sub.order_by("-created_at", "-id").first()
        created_by_name = _display_name(
            getattr(last_run, "created_by", None) or
            (last_run.config.owner if last_run else None)
        )

        cat_summary.append({
            "id": c.id,
            "name": c.name,
            "runs": runs,
            "success": sub.filter(status="success").count(),
            "failed": sub.filter(status="failed").count(),
            "diffs": sub.aggregate(s=Sum("diff_rows"))["s"] or 0,
            "integrated_runs": sub.filter(status="success", diff_rows=0).count(),
            "created_by": created_by_name,  # ⬅️ utilisé par le template (“Créé par : …”)
        })

    # ---------- Résumés par magasin (cartes) ----------
    per_store_map: dict[str, dict] = defaultdict(
        lambda: {"code": "", "name": "", "runs": 0, "success": 0, "failed": 0, "diffs": 0}
    )
    for r in qs:
        ds = r.dataset_web1 or r.dataset_desktop
        code = (getattr(ds, "store_code", "") or "").strip()
        name = (getattr(ds, "store_name", "") or "").strip()
        if not code and not name:
            code = ""  # clé pour "sans magasin"

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
    per_store.sort(key=lambda x: (x["code"] or "~~~~", x["name"] or ""))  # codes vides à la fin

    # Enrichissement “Créé par” pour chaque magasin (dernier run de ce magasin)
    for s in per_store:
        code = s.get("code")
        if not code:
            s["created_by"] = None
            continue
        last_run = (
            qs.filter(Q(dataset_web1__store_code=code) | Q(dataset_desktop__store_code=code))
              .order_by("-created_at", "-id")
              .first()
        )
        s["created_by"] = _display_name(
            getattr(last_run, "created_by", None) or
            (last_run.config.owner if last_run else None)
        ) if last_run else None

    # ---------- Graphiques (agrégats mensuels) ----------
    months: list[str] = []
    per_month_runs: dict[str, int] = defaultdict(int)
    per_month_diffs: dict[str, int] = defaultdict(int)

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

    # ---------- Derniers runs ----------
    recent_runs = list(qs[:10])

    # ---------- Propriétaires (select “Utilisateur”) ----------
    owners = (
        list(User.objects.order_by("username").values("id", "username"))
        if request.user.is_staff else []
    )

    # ---------- Contexte ----------
    ctx = {
        "start": start,
        "end": end,

        # Filtres
        "categories": categories,
        "stores": stores,

        # KPI & cartes
        "kpis": kpis,
        "cat_summary": cat_summary,
        "per_store": per_store if stores else [],
        "recent_runs": recent_runs,

        # Graphs (JSON prêt pour Chart.js)
        "labels_json": json.dumps(labels),
        "runs_series_json": json.dumps(runs_series),
        "diffs_series_json": json.dumps(diffs_series),
        "has_line_data": bool(labels),
        "status_labels_json": json.dumps(status_labels),
        "status_values_json": json.dumps(status_values),
        "has_donut_data": any(status_values),

        # Sélections courantes
        "selected_category": cat_id,
        "selected_store": store_code,
        "selected_owner": str(selected_owner) if selected_owner else "",

        # Select Utilisateur (admin)
        "owners": owners,
    }
    return render(request, "dashboards/home.html", ctx)
