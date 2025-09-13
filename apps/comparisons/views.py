# apps/comparisons/views.py
from __future__ import annotations

import re
import uuid
from pathlib import Path
from datetime import timedelta
from collections import defaultdict

import pandas as pd
from pandas.api.types import is_categorical_dtype, is_datetime64_any_dtype

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date

from .exporters import to_csv, to_xlsx
from .models import CompareResult, CompareRun
from .services import compute_diff
from apps.configs.models import CompareConfig
from apps.datasets.models import Dataset
from apps.datasets.services import sniff_sep_and_encoding
from io import BytesIO
from django.core.files.storage import default_storage


User = get_user_model()

# ---------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------

# Caractères interdits par Excel (openpyxl/XML)
_ILLEGAL_XLSX_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')

def _sanitize_for_export(df: pd.DataFrame) -> pd.DataFrame:
    """Prépare un DataFrame pour export Excel/CSV."""
    safe = df.drop(columns=["_merge"], errors="ignore").copy()
    for col in safe.columns:
        s = safe[col]
        if is_categorical_dtype(s.dtype) or is_datetime64_any_dtype(s.dtype):
            safe[col] = s.astype("string")
    safe = safe.astype("string").fillna("")
    safe.columns = [_ILLEGAL_XLSX_RE.sub("", str(c)) for c in safe.columns]
    for col in safe.columns:
        safe[col] = safe[col].str.replace(_ILLEGAL_XLSX_RE, "", regex=True)
    return safe

def _display_name(user) -> str | None:
    """Retourne 'Prénom Nom' si dispo, sinon username, sinon None."""
    if not user:
        return None
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or getattr(user, "username", None)

# ---------------------------------------------------------------------
# Création d'un run depuis la session (toujours limité au propriétaire)
# ---------------------------------------------------------------------

@login_required
def run_with_session(request):
    """
    Lance une comparaison à partir du contexte de session.
    Création d'un run pour l'utilisateur courant uniquement.
    """
    ctx = request.session.get("upload_context")
    cfg_id = request.session.get("config_id")
    if not (ctx and cfg_id):
        messages.error(request, "Paramètres manquants.")
        return redirect("datasets:upload")

    cfg = get_object_or_404(CompareConfig, id=cfg_id, owner=request.user)
    ds1 = get_object_or_404(Dataset, id=ctx["dataset_web1_id"], owner=request.user)
    ds2 = get_object_or_404(Dataset, id=ctx["dataset_desktop_id"], owner=request.user)

    # Lecture robuste CSV 1
    try:
        with open(ds1.file.path, "rb") as f1:
            sep1, enc1 = sniff_sep_and_encoding(f1)
        df1 = pd.read_csv(ds1.file.path, dtype=str, sep=sep1, encoding=enc1, engine="python")
    except Exception as e:
        messages.error(request, f"Erreur lecture CSV (Web1) : {e}")
        return redirect("datasets:upload")

    # Lecture robuste CSV 2
    try:
        with open(ds2.file.path, "rb") as f2:
            sep2, enc2 = sniff_sep_and_encoding(f2)
        df2 = pd.read_csv(ds2.file.path, dtype=str, sep=sep2, encoding=enc2, engine="python")
    except Exception as e:
        messages.error(request, f"Erreur lecture CSV (Desktop) : {e}")
        return redirect("datasets:upload")

    run = CompareRun.objects.create(
        config=cfg,
        dataset_web1=ds1,
        dataset_desktop=ds2,
        status="running",
    )

    try:
        diff = compute_diff(df1, df2, cfg)

        # Normaliser types
        for col in diff.columns:
            s = diff[col]
            if is_categorical_dtype(s.dtype) or is_datetime64_any_dtype(s.dtype):
                diff[col] = s.astype("string")
        diff = diff.where(pd.notna(diff), "")

        run.total_rows = (len(df1) if df1 is not None else 0) + (len(df2) if df2 is not None else 0)
        run.diff_rows = len(diff)
        run.status = "success"
        run.finished_at = timezone.now()

        # Aperçu JSON
        payload = diff.head(10000).to_dict(orient="records")
        CompareResult.objects.create(run=run, payload=payload)

        # Exports
        export_df = _sanitize_for_export(diff)
        out_dir: Path = Path(settings.MEDIA_ROOT) / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        base = f"diff_{run.id}_{uuid.uuid4().hex}"
        csv_path = out_dir / f"{base}.csv"
        xlsx_path = out_dir / f"{base}.xlsx"

        to_csv(export_df, csv_path)
        to_xlsx(export_df, xlsx_path)

        url_csv = f"{settings.MEDIA_URL}exports/{base}.csv"
        url_xlsx = f"{settings.MEDIA_URL}exports/{base}.xlsx"

        # session + persistance
        request.session["last_export"] = {"csv": url_csv, "xlsx": url_xlsx}
        run.export_csv = url_csv
        run.export_xlsx = url_xlsx
        run.save(update_fields=["total_rows", "diff_rows", "status", "finished_at", "export_csv", "export_xlsx"])

    except Exception as e:
        run.status = "failed"
        run.message = str(e)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "message", "finished_at"])
        messages.error(request, f"Erreur comparaison : {e}")
        return redirect("datasets:upload")

    return redirect("comparisons:results", run_id=run.id)

# ---------------------------------------------------------------------
# Affichage des résultats d'un run
#   - Admin : accès à tous
#   - Non-admin : accès seulement à ses propres runs
# ---------------------------------------------------------------------

@login_required
def results(request, run_id):
    """
    - Admin : accès global
    - Non-admin : accès limité à ses runs
    """
    if request.user.is_staff:
        run = get_object_or_404(CompareRun, id=run_id)
    else:
        run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)

    res = get_object_or_404(CompareResult, run=run)
    exports = request.session.get("last_export", {})
    columns = list(res.payload[0].keys()) if res.payload else []
    rows = res.payload[:200] if res.payload else []

    ds = run.dataset_web1 or run.dataset_desktop
    store_code = getattr(ds, "store_code", None)
    store_name = getattr(ds, "store_name", None)

    return render(request, "comparisons/results.html", {
        "run": run,
        "columns": columns,
        "rows": rows,
        "exports": exports,
        "has_diff": bool(run.diff_rows),
        "store_code": store_code,
        "store_name": store_name,
    })


@login_required
def runs_dashboard(request):
    """
    - Admin : voit tous les runs
    - Non-admin : ne voit que ses runs
    """
    base_qs = (
        CompareRun.objects
        .select_related("config", "config__category", "config__owner",
                        "dataset_web1", "dataset_desktop")
        .order_by("-created_at", "-id")
    )
    if request.user.is_staff:
        qs = base_qs
    else:
        qs = base_qs.filter(config__owner=request.user)

    # --- Filtres ---
    cat_param = request.GET.get("category")
    cfg_id    = request.GET.get("config")
    status    = request.GET.get("status")
    store     = (request.GET.get("store") or "").strip()

    if cat_param:
        if str(cat_param).isdigit():
            qs = qs.filter(config__category_id=cat_param)
            selected_category = str(cat_param)
        else:
            from apps.catalogs.models import ConfigCategory
            qs = qs.filter(config__category__name__iexact=cat_param)
            sel_id = ConfigCategory.objects.filter(
                name__iexact=cat_param
            ).values_list("id", flat=True).first()
            selected_category = str(sel_id or "")
    else:
        selected_category = ""

    if cfg_id:
        qs = qs.filter(config_id=cfg_id)
    if status:
        qs = qs.filter(status=status)
    if store:
        qs = qs.filter(
            Q(dataset_web1__store_code=store) |
            Q(dataset_desktop__store_code=store)
        )

    # --- Stats ---
    stats = {
        "total":   qs.count(),
        "success": qs.filter(status="success").count(),
        "failed":  qs.filter(status="failed").count(),
        "rows":    qs.aggregate(total_rows=Sum("total_rows"))["total_rows"] or 0,
        "diffs":   qs.aggregate(total_diffs=Sum("diff_rows"))["total_diffs"] or 0,
    }

    # --- Listes pour filtres ---
    from apps.catalogs.models import ConfigCategory
    from apps.configs.models import CompareConfig as Cfg
    categories = ConfigCategory.objects.all().order_by("name")
    configs = (Cfg.objects.all() if request.user.is_staff
               else Cfg.objects.filter(owner=request.user)).order_by("name")

    # --- Magasins (depuis qs filtré) ---
    stores, seen = [], set()
    web1_pairs = qs.values_list("dataset_web1__store_code", "dataset_web1__store_name")
    desk_pairs = qs.values_list("dataset_desktop__store_code", "dataset_desktop__store_name")
    for code, name in list(web1_pairs) + list(desk_pairs):
        code = (code or "").strip()
        name = (name or "").strip()
        if not code and not name:
            continue
        key = (code, name)
        if key in seen:
            continue
        seen.add(key)
        stores.append({"code": code, "name": name})
    stores.sort(key=lambda x: (x["code"] or "", x["name"] or ""))

    runs = list(qs[:200])
    status_choices = ["running", "success", "failed"]

    return render(request, "comparisons/runs_dashboard.html", {
        "runs": runs,
        "stats": stats,
        "categories": categories,
        "configs": configs,
        "status_choices": status_choices,
        "stores": stores,
        "selected": {
            "category": selected_category,
            "config":   cfg_id or "",
            "status":   status or "",
            "store":    store or "",
        },
    })
    
    
@login_required
def latest_for_category(request):
    cat_id = request.GET.get("category")
    start = parse_date(request.GET.get("start") or "")
    end   = parse_date(request.GET.get("end") or "")
    store = (request.GET.get("store") or "").strip()

    if request.user.is_staff:
        qs = CompareRun.objects.select_related("config", "config__category",
                                               "dataset_web1", "dataset_desktop")
        owner = (request.GET.get("owner") or "").strip()
        if owner:
            qs = qs.filter(config__owner_id=owner)
    else:
        qs = CompareRun.objects.filter(config__owner=request.user)\
                               .select_related("config", "config__category",
                                               "dataset_web1", "dataset_desktop")

    if cat_id:
        qs = qs.filter(config__category_id=cat_id)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if store:
        qs = qs.filter(Q(dataset_web1__store_code=store) | Q(dataset_desktop__store_code=store))

    qs = qs.order_by("-created_at")

    # On privilégie un run "success" avec écarts
    run = qs.filter(status="success", diff_rows__gt=0).first() or qs.first()
    if run:
        return redirect("comparisons:results", run_id=run.id)

    messages.info(request, "Aucun run trouvé pour les filtres sélectionnés.")
    return redirect("comparisons:runs_dashboard")

# ---------------------------------------------------------------------
# Page synthèse (lecture dataset) — admin autorisé sur tous les runs
# ---------------------------------------------------------------------

def _guess_col(columns, patterns):
    cols = [c for c in columns]
    low  = [c.lower() for c in columns]
    for p in patterns:
        p = p.lower()
        for i, name in enumerate(low):
            if p in name:
                return cols[i]
    return None

def _fmt_date_col(series):
    s = series.fillna("").astype(str).str.strip()
    try:
        s2 = pd.to_datetime(s, errors="coerce", dayfirst=True)
        s2 = s2.dt.strftime("%d/%m/%Y")
        s2 = s2.fillna(s)
        return s2
    except Exception:
        return s

def _group_count(df, by_col, title_fmt=None):
    s = df[by_col].fillna("").astype(str).str.strip()
    grp = s.value_counts(dropna=False).reset_index()
    grp.columns = ["label", "count"]
    grp["label"] = grp["label"].replace({"": "(vide)"})
    rows = list(grp.itertuples(index=False, name=None))
    total = int(grp["count"].sum()) if not grp.empty else 0
    if title_fmt:
        rows = [(title_fmt(lbl), cnt) for (lbl, cnt) in rows]
    return rows, total

@login_required
def summary_orders(request, run_id):
    """
    Page synthèse pour un run.
    - Admin : accès global
    - Non-admin : accès limité à ses runs
    Lecture robuste du CSV via le storage, avec fallback Web1 -> Desktop.
    """
    # Sécurité d'accès
    if request.user.is_staff:
        run = get_object_or_404(CompareRun, id=run_id)
    else:
        run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)

    # On tente d'abord le dataset Web1, puis Desktop en fallback
    primary = run.dataset_web1 or run.dataset_desktop
    df, err = _read_dataset_dataframe(primary)

    if err == "missing" and run.dataset_desktop and primary is not run.dataset_desktop:
        df, err = _read_dataset_dataframe(run.dataset_desktop)

    if err == "missing" or df is None:
        messages.error(
            request,
            "Le fichier source de ce comparatif n'existe plus sur le disque. "
            "Réimportez les CSV et relancez le comparatif."
        )
        return redirect("comparisons:results", run_id=run.id)

    columns = list(df.columns)

    # Auto-guess des colonnes
    guess_date_cmd = _guess_col(columns, ["date commande", "date_commande", "date cmd", "créé le", "date creation", "date"])
    guess_date_liv = _guess_col(columns, ["date livraison", "date livr", "livraison", "deliv"])
    guess_store    = _guess_col(columns, ["magasin", "nommagasin", "nommag", "store", "site", "ncde"])

    date_cmd_col = request.GET.get("date_cmd") or guess_date_cmd
    date_liv_col = request.GET.get("date_liv") or guess_date_liv
    store_col    = request.GET.get("store")    or guess_store

    sections = []

    # 1) PÉRIODE (par date commande)
    if date_cmd_col and date_cmd_col in df.columns:
        tmp = df.copy()
        tmp["_period"] = _fmt_date_col(tmp[date_cmd_col])
        rows, total = _group_count(tmp, "_period")
        sections.append({
            "title": "PÉRIODE",
            "rows": rows,
            "total": total,
            "right": "NOMBRE COMMANDE",
        })

    # 2) MAGASIN
    if store_col and store_col in df.columns:
        rows, total = _group_count(df, store_col)
        sections.append({
            "title": "MAGASIN",
            "rows": rows,
            "total": total,
            "right": "NOMBRE  COMMANDE",
        })

    # 3) DATE DE LIVRAISON
    if date_liv_col and date_liv_col in df.columns:
        tmp = df.copy()
        tmp["_liv"] = _fmt_date_col(tmp[date_liv_col])
        rows, total = _group_count(tmp, "_liv")
        sections.append({
            "title": "DATE DE LIVRESON",
            "rows": rows,
            "total": total,
            "right": "NOMBRE COMMANDE",
        })

    ctx = {
        "run": run,
        "columns": columns,
        "date_cmd_col": date_cmd_col,
        "date_liv_col": date_liv_col,
        "store_col":    store_col,
        "sections": sections,
        "has_data": any(s["rows"] for s in sections),
    }
    return render(request, "comparisons/summary_orders.html", ctx)


# ---------------------------------------------------------------------
# Edition / suppression (on laisse restreint au propriétaire)
# ---------------------------------------------------------------------

@login_required
def run_edit(request, run_id):
    """
    - Admin : peut éditer n'importe quel run
    - Non-admin : uniquement ses runs
    """
    if request.user.is_staff:
        run = get_object_or_404(CompareRun, id=run_id)
    else:
        run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)

    if request.method == "POST":
        run.message = (request.POST.get("message") or "").strip()
        run.save(update_fields=["message"])
        messages.success(request, f"Comparatif #{run.id} mis à jour.")
        return redirect("comparisons:runs_dashboard")

    return render(request, "comparisons/run_edit.html", {"run": run})

@login_required
def run_delete(request, run_id):
    """
    - Admin : peut supprimer n'importe quel run
    - Non-admin : uniquement ses runs
    """
    if request.user.is_staff:
        run = get_object_or_404(CompareRun, id=run_id)
    else:
        run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)

    if request.method == "POST":
        rid = run.id
        run.delete()
        messages.success(request, f"Comparatif #{rid} supprimé.")
        return redirect("comparisons:runs_dashboard")

    # Fallback GET (confirmation simple)
    return render(request, "comparisons/run_confirm_delete.html", {"run": run})

@login_required
def run_bulk_delete(request):
    """
    Suppression multiple.
    - Admin : global
    - Non-admin : limité à ses runs
    """
    if request.method != "POST":
        return redirect("comparisons:runs_dashboard")

    ids = request.POST.getlist("selected")
    if not ids:
        messages.info(request, "Aucun élément sélectionné.")
        return redirect("comparisons:runs_dashboard")

    qs = CompareRun.objects.filter(id__in=ids)
    if not request.user.is_staff:
        qs = qs.filter(config__owner=request.user)

    count = qs.count()
    qs.delete()
    messages.success(request, f"{count} comparatif(s) supprimé(s).")
    return redirect("comparisons:runs_dashboard")


def _read_dataset_dataframe(ds):
    """
    Ouvre le fichier d'un Dataset via son storage et renvoie (df, error).
    error vaut 'missing' si le fichier n'existe plus.
    """
    if not ds or not getattr(ds, "file", None):
        return None, "missing"

    storage = getattr(ds.file, "storage", default_storage)
    name = getattr(ds.file, "name", None)

    if not name or not storage.exists(name):
        return None, "missing"

    # Lecture binaire puis détection encodage/séparateur sur un buffer mémoire
    with storage.open(name, "rb") as fh:
        raw = fh.read()
    buf = BytesIO(raw)

    sep, enc = sniff_sep_and_encoding(BytesIO(raw))
    df = pd.read_csv(buf, dtype=str, sep=sep, encoding=enc, engine="python")
    return df, None
