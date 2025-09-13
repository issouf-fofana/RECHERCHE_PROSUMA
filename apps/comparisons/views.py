# apps/comparisons/views.py
import re
import uuid
from pathlib import Path

import pandas as pd
from pandas.api.types import is_categorical_dtype, is_datetime64_any_dtype

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .exporters import to_csv, to_xlsx
from .models import CompareResult, CompareRun
from .services import compute_diff
from apps.configs.models import CompareConfig
from apps.datasets.models import Dataset
from apps.datasets.services import sniff_sep_and_encoding


# Caractères interdits par Excel (openpyxl/XML)
_ILLEGAL_XLSX_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F]')


def _sanitize_for_export(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prépare un DataFrame pour export Excel/CSV :
    - supprime la colonne _merge si présente
    - convertit colonnes catégorielles/datetime en string
    - remplace NA par ""
    - supprime les caractères interdits dans colonnes et cellules
    """
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


@login_required
def run_with_session(request):
    """
    Lance une comparaison à partir du contexte de session (datasets + config).
    Stocke le run, un aperçu JSON des écarts et les chemins d'export.
    """
    ctx = request.session.get("upload_context")
    cfg_id = request.session.get("config_id")
    if not (ctx and cfg_id):
        messages.error(request, "Paramètres manquants.")
        return redirect("datasets:upload")

    cfg = get_object_or_404(CompareConfig, id=cfg_id, owner=request.user)
    ds1 = get_object_or_404(Dataset, id=ctx["dataset_web1_id"], owner=request.user)
    ds2 = get_object_or_404(Dataset, id=ctx["dataset_desktop_id"], owner=request.user)

    # --- Lecture robuste des deux CSV ---
    try:
        with open(ds1.file.path, "rb") as f1:
            sep1, enc1 = sniff_sep_and_encoding(f1)
        df1 = pd.read_csv(ds1.file.path, dtype=str, sep=sep1, encoding=enc1, engine="python")
    except Exception as e:
        messages.error(request, f"Erreur lecture CSV (Web1) : {e}")
        return redirect("datasets:upload")

    try:
        with open(ds2.file.path, "rb") as f2:
            sep2, enc2 = sniff_sep_and_encoding(f2)
        df2 = pd.read_csv(ds2.file.path, dtype=str, sep=sep2, encoding=enc2, engine="python")
    except Exception as e:
        messages.error(request, f"Erreur lecture CSV (Desktop) : {e}")
        return redirect("datasets:upload")
    # ------------------------------------

    run = CompareRun.objects.create(
        config=cfg,
        dataset_web1=ds1,
        dataset_desktop=ds2,
        status="running",
    )

    try:
        diff = compute_diff(df1, df2, cfg)

        # Normaliser types pour éviter les soucis de colonnes catégorielles (ex: _merge)
        for col in diff.columns:
            s = diff[col]
            if is_categorical_dtype(s.dtype) or is_datetime64_any_dtype(s.dtype):
                diff[col] = s.astype("string")

        # Remplacer NA/NaN par vide (après normalisation)
        diff = diff.where(pd.notna(diff), "")

        run.total_rows = (len(df1) if df1 is not None else 0) + (len(df2) if df2 is not None else 0)
        run.diff_rows = len(diff)
        run.status = "success"
        run.finished_at = timezone.now()

        # Sauvegarde d’un aperçu JSON (pour affichage rapide)
        payload = diff.head(10000).to_dict(orient="records")
        CompareResult.objects.create(run=run, payload=payload)

        # Exports (CSV/XLSX) sur DataFrame nettoyé
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

        # session (pour la page résultats) + stockage sur le run (pour le dashboard)
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


@login_required
def results(request, run_id):
    """
    Page résultats : affiche un aperçu (≤ 200 lignes) et propose les exports.
    """
    run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)
    res = get_object_or_404(CompareResult, run=run)

    # Préférence à la session, sinon fallback sur ce qui est stocké sur le run
    exports = request.session.get("last_export", {}) or {}
    if not exports.get("csv") and getattr(run, "export_csv", None):
        exports["csv"] = run.export_csv
    if not exports.get("xlsx") and getattr(run, "export_xlsx", None):
        exports["xlsx"] = run.export_xlsx

    columns = list(res.payload[0].keys()) if res.payload else []
    rows = res.payload[:200] if res.payload else []

    return render(request, "comparisons/results.html", {
        "run": run,
        "columns": columns,
        "rows": rows,
        "exports": exports,
        "has_diff": bool(run.diff_rows),
    })


@login_required
def runs_dashboard(request):
    qs = (CompareRun.objects
          .filter(config__owner=request.user)
          .select_related("config", "config__category")
          .order_by("-created_at", "-id"))

    cat_id = request.GET.get("category")
    cfg_id = request.GET.get("config")
    status = request.GET.get("status")

    if cat_id:
        qs = qs.filter(config__category_id=cat_id)
    if cfg_id:
        qs = qs.filter(config_id=cfg_id)
    if status:
        qs = qs.filter(status=status)

    stats = {
        "total": qs.count(),
        "success": qs.filter(status="success").count(),
        "failed": qs.filter(status="failed").count(),
        "rows": qs.aggregate(total_rows=Sum("total_rows"))["total_rows"] or 0,
        "diffs": qs.aggregate(total_diffs=Sum("diff_rows"))["total_diffs"] or 0,
    }

    from apps.catalogs.models import ConfigCategory
    from apps.configs.models import CompareConfig as Cfg
    categories = ConfigCategory.objects.all().order_by("name")
    configs = Cfg.objects.filter(owner=request.user).order_by("name")

    runs = list(qs[:200])
    status_choices = ["running", "success", "failed"]   # 👈 ajouté

    return render(request, "comparisons/runs_dashboard.html", {
        "runs": runs,
        "stats": stats,
        "categories": categories,
        "configs": configs,
        "selected": {"category": cat_id, "config": cfg_id, "status": status},
        "status_choices": status_choices,                # 👈 ajouté
    })
