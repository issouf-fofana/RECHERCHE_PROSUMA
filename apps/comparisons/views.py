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
    run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)
    res = get_object_or_404(CompareResult, run=run)
    exports = request.session.get("last_export", {})
    columns = list(res.payload[0].keys()) if res.payload else []
    rows = res.payload[:200] if res.payload else []

    # ✅ infos magasin (depuis ds web1 prioritaire)
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


# apps/comparisons/views.py (extrait : runs_dashboard)
from django.db.models import Sum, Q
from django.contrib import messages
# ... autres imports

from django.contrib.auth import get_user_model
User = get_user_model()

# apps/comparisons/views.py
from django.db.models import Sum, Q
from django.contrib import messages
from django.shortcuts import render

@login_required
def runs_dashboard(request):
    qs = (
        CompareRun.objects
        .filter(config__owner=request.user)
        .select_related("config", "config__category", "dataset_web1", "dataset_desktop")
        .order_by("-created_at", "-id")
    )

    # --- Filtres ---
    cat_param = request.GET.get("category")
    cfg_id    = request.GET.get("config")
    status    = request.GET.get("status")
    store     = (request.GET.get("store") or "").strip()  # code magasin (ex "230")

    # Catégorie (id ou nom)
    if cat_param:
        if str(cat_param).isdigit():
            qs = qs.filter(config__category_id=cat_param)
            selected_category = str(cat_param)
        else:
            from apps.catalogs.models import ConfigCategory
            qs = qs.filter(config__category__name__iexact=cat_param)
            sel_id = ConfigCategory.objects.filter(name__iexact=cat_param).values_list("id", flat=True).first()
            selected_category = str(sel_id or "")
    else:
        selected_category = ""

    # Config
    if cfg_id:
        qs = qs.filter(config_id=cfg_id)

    # Statut
    if status:
        qs = qs.filter(status=status)

    # Magasin (code) sur Web1 OU Desktop
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
    configs    = Cfg.objects.filter(owner=request.user).order_by("name")

    # --- Magasins disponibles (dédoublés) À PARTIR DE QS (pas 'runs') ---
    stores = []
    seen = set()

    # On interroge directement la DB pour éviter d’itérer sur des objets lourds
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

    # --- Jeu affiché ---
    runs = list(qs[:200])  # ICI seulement on définit 'runs'

    status_choices = ["running", "success", "failed"]

    return render(request, "comparisons/runs_dashboard.html", {
        "runs": runs,
        "stats": stats,
        "categories": categories,
        "configs": configs,
        "status_choices": status_choices,
        "stores": stores,  # [{'code': '230', 'name': 'CASINO PRIMA'}, ...]
        "selected": {
            "category": selected_category,
            "config":   cfg_id or "",
            "status":   status or "",
            "store":    store or "",
        },
    })

from django.db.models import Q
from django.utils.dateparse import parse_date
from django.contrib import messages

@login_required
def latest_for_category(request):
    """
    Ouvre le dernier run (idéalement avec écarts) pour la catégorie/période/magasin sélectionnés.
    Si aucun run, redirige vers la liste avec un message.
    """
    cat_id = request.GET.get("category")
    start = parse_date(request.GET.get("start") or "")
    end = parse_date(request.GET.get("end") or "")
    store = (request.GET.get("store") or "").strip()

    qs = CompareRun.objects.filter(config__owner=request.user).select_related(
        "config", "config__category", "dataset_web1", "dataset_desktop"
    )

    if cat_id:
        qs = qs.filter(config__category_id=cat_id)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if store:
        qs = qs.filter(
            Q(dataset_web1__store_code=store) | Q(dataset_desktop__store_code=store)
        )

    qs = qs.order_by("-created_at")

    # On privilégie un run "success" avec des écarts
    run = qs.filter(status="success", diff_rows__gt=0).first()
    if not run:
        run = qs.first()

    if run:
        return redirect("comparisons:results", run_id=run.id)

    messages.info(request, "Aucun run trouvé pour les filtres sélectionnés.")
    return redirect("comparisons:runs_dashboard")


# apps/comparisons/views.py
from pathlib import Path
import pandas as pd
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from .models import CompareRun, CompareResult
from apps.datasets.services import sniff_sep_and_encoding

def _guess_col(columns, patterns):
    """Retourne la première colonne dont le nom contient un des motifs."""
    cols = [c for c in columns]
    low  = [c.lower() for c in columns]
    for p in patterns:
        p = p.lower()
        for i, name in enumerate(low):
            if p in name:
                return cols[i]
    return None

def _fmt_date_col(series):
    """Essaie de parser en date et formate dd/mm/YYYY, sinon renvoie du texte brut."""
    s = series.fillna("").astype(str).str.strip()
    try:
        s2 = pd.to_datetime(s, errors="coerce", dayfirst=True)
        s2 = s2.dt.strftime("%d/%m/%Y")
        s2 = s2.fillna(s)  # garde texte si non parse
        return s2
    except Exception:
        return s

def _group_count(df, by_col, title_fmt=None):
    """Regroupe et renvoie (list of (label, count), total)."""
    s = df[by_col].fillna("").astype(str).str.strip()
    grp = s.value_counts(dropna=False).reset_index()
    grp.columns = ["label", "count"]
    # nettoyage label vide
    grp["label"] = grp["label"].replace({"": "(vide)"})
    rows = list(grp.itertuples(index=False, name=None))
    total = int(grp["count"].sum()) if not grp.empty else 0
    if title_fmt:
        rows = [(title_fmt(lbl), cnt) for (lbl, cnt) in rows]
    return rows, total

@login_required
def summary_orders(request, run_id):
    """
    Page synthèse pour un run :
    - Période (par 'date commande' choisie)
    - Magasin (code/nom)
    - Date de livraison
    On laisse l’utilisateur choisir les colonnes à utiliser via des <select>.
    """
    run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)
    ds1 = run.dataset_web1
    if not ds1:
        messages.error(request, "Dataset Web1 introuvable pour ce comparatif.")
        return redirect("comparisons:results", run_id=run.id)

    # lecture robuste
    with open(ds1.file.path, "rb") as f:
        sep, enc = sniff_sep_and_encoding(f)
    df = pd.read_csv(ds1.file.path, dtype=str, sep=sep, encoding=enc, engine="python")
    columns = list(df.columns)

    # valeurs proposées / auto-guess
    guess_date_cmd = _guess_col(columns, ["date commande", "date_commande", "date cmd", "créé le", "date creation", "date"])
    guess_date_liv = _guess_col(columns, ["date livraison", "date livr", "livraison", "deliv"])
    guess_store    = _guess_col(columns, ["magasin", "nommagasin", "nommag", "store", "site", "ncde"])

    date_cmd_col = request.GET.get("date_cmd") or guess_date_cmd
    date_liv_col = request.GET.get("date_liv") or guess_date_liv
    store_col    = request.GET.get("store")    or guess_store

    # sections
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
from .forms import RunEditForm


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from .models import CompareRun

@login_required
def run_edit(request, run_id):
    """
    Edition simple: on édite 'message' (notes) via la modale.
    """
    run = get_object_or_404(CompareRun, id=run_id, config__owner=request.user)
    if request.method == "POST":
        new_message = (request.POST.get("message") or "").strip()
        run.message = new_message
        run.save(update_fields=["message"])
        messages.success(request, f"Comparatif #{run.id} mis à jour.")
        return redirect("comparisons:runs_dashboard")

    # Fallback GET (si on ouvre l’URL directement)
    return render(request, "comparisons/run_edit.html", {"run": run})

@login_required
def run_delete(request, run_id):
    """
    Suppression d'un comparatif (POST depuis modale).
    """
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
    Suppression multiple depuis cases à cocher (si tu l’ajoutes plus tard).
    """
    if request.method != "POST":
        return redirect("comparisons:runs_dashboard")

    ids = request.POST.getlist("selected")
    if not ids:
        messages.info(request, "Aucun élément sélectionné.")
        return redirect("comparisons:runs_dashboard")

    runs = CompareRun.objects.filter(id__in=ids, config__owner=request.user)
    count = runs.count()
    runs.delete()
    messages.success(request, f"{count} comparatif(s) supprimé(s).")
    return redirect("comparisons:runs_dashboard")