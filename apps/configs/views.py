from __future__ import annotations

import os
from io import BytesIO

import pandas as pd
from django import forms as djforms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.storage import default_storage

from .models import CompareConfig
from .forms import ConfigNameForm
from .services import validate_columns
from apps.catalogs.models import ConfigCategory
from apps.datasets.models import Dataset
from apps.datasets.services import sniff_sep  # détection séparateur CSV

# ------- Helpers lecture fichiers (CSV/XLS/XLSX) avec ligne d’entêtes --------

_ENCODING_CANDIDATES = ["utf-8-sig", "utf-8", "cp1252", "latin1", "mac_roman"]


def _read_csv_robust(raw: bytes, *, header: int | None = 0) -> pd.DataFrame:
    """Lecture CSV tolérante (multi-encodages) + sniff du séparateur."""
    sep = sniff_sep(BytesIO(raw))
    last = None
    for enc in _ENCODING_CANDIDATES:
        try:
            return pd.read_csv(
                BytesIO(raw),
                dtype=str,
                sep=sep,
                encoding=enc,
                engine="python",
                header=header,
            )
        except UnicodeDecodeError as e:
            last = e
            continue
    raise UnicodeDecodeError("enc", b"", 0, 1, f"Impossible de décoder le CSV ({last})")


def _read_for_preview(ds: Dataset, *, header_row: int = 0, nrows: int = 8) -> pd.DataFrame:
    """Lit le fichier d’un Dataset pour l’aperçu, avec la ligne d’entêtes choisie."""
    storage = getattr(ds.file, "storage", default_storage)
    name = getattr(ds.file, "name", None)
    if not name or not storage.exists(name):
        raise FileNotFoundError("Fichier introuvable pour l’aperçu.")

    with storage.open(name, "rb") as fh:
        raw = fh.read()

    ext = os.path.splitext(name)[1].lower()
    if ext == ".csv":
        df = _read_csv_robust(raw, header=header_row)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(BytesIO(raw), dtype=str, sheet_name=0, header=header_row)
    else:
        raise ValueError(f"Extension non prise en charge: {ext}")

    df.columns = [str(c) for c in df.columns]
    return df.head(nrows)


def _dedup(seq):
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


# ----------------------------- Vue principale -----------------------------

@login_required
def choose_columns(request):
    """
    Écran de configuration :
      - Étape 1 : choisir la ligne d’entêtes pour Web1/Desktop (prévisualisation live)
      - Étape 2+ : choisir colonnes à garder, clés, type de jointure
    Les entêtes choisies et la ligne d’entêtes sont stockées en session pour la suite.
    """
    ctx = request.session.get("upload_context")
    if not ctx:
        messages.error(request, "Commence par charger deux fichiers.")
        return redirect("datasets:upload")

    # 1) Récupérer datasets
    ds_web1 = get_object_or_404(Dataset, id=ctx["dataset_web1_id"], owner=request.user)
    ds_desk = get_object_or_404(Dataset, id=ctx["dataset_desktop_id"], owner=request.user)

    # 2) Ligne d’entêtes (0-based en interne)
    header_rows = ctx.get("header_rows") or {"web1": 0, "desktop": 0}
    try:
        h_web1 = int(request.POST.get("header_web1", header_rows.get("web1", 0)))
    except Exception:
        h_web1 = 0
    try:
        h_desk = int(request.POST.get("header_desktop", header_rows.get("desktop", 0)))
    except Exception:
        h_desk = 0

    # 3) Lire des aperçus avec la ligne d’entêtes choisie
    try:
        prev_web1 = _read_for_preview(ds_web1, header_row=h_web1, nrows=8)
        prev_desk = _read_for_preview(ds_desk, header_row=h_desk, nrows=8)
    except Exception as e:
        messages.error(request, f"Erreur de lecture: {e}")
        return redirect("datasets:upload")

    # 4) Si on clique "Appliquer", on fige les entêtes et on reste sur la page
    if request.method == "POST" and request.POST.get("action") == "apply_headers":
        ctx["headers"] = {"web1": list(prev_web1.columns), "desktop": list(prev_desk.columns)}
        ctx["header_rows"] = {"web1": h_web1, "desktop": h_desk}
        request.session["upload_context"] = ctx
        messages.success(request, "Entêtes mises à jour.")
        # on continue pour reconstruire le formulaire avec les nouvelles entêtes

    # 5) Construit le formulaire dynamique à partir des entêtes courantes
    headers = ctx.get("headers") or {"web1": list(prev_web1.columns), "desktop": list(prev_desk.columns)}

    def build_dynamic_fields(form):
        # bloc entêtes : listes déroulantes 1..20 (affiché en haut du template)
        form.fields["header_web1"] = djforms.ChoiceField(
            label="Ligne d’entêtes (Web1)",
            choices=[(i, f"Ligne {i+1}") for i in range(20)],
            initial=h_web1,
            widget=djforms.Select(attrs={"class": "form-select"})
        )
        form.fields["header_desktop"] = djforms.ChoiceField(
            label="Ligne d’entêtes (Desktop)",
            choices=[(i, f"Ligne {i+1}") for i in range(20)],
            initial=h_desk,
            widget=djforms.Select(attrs={"class": "form-select"})
        )

        # colonnes et clés
        form.fields["columns_web1"] = djforms.MultipleChoiceField(
            label="Colonnes à garder (Web1)",
            choices=[(h, h) for h in headers["web1"]],
            widget=djforms.CheckboxSelectMultiple
        )
        form.fields["columns_desktop"] = djforms.MultipleChoiceField(
            label="Colonnes à garder (Desktop)",
            choices=[(h, h) for h in headers["desktop"]],
            widget=djforms.CheckboxSelectMultiple
        )
        form.fields["join_key_web1"] = djforms.MultipleChoiceField(
            label="Clés (Web1) — ordre = priorité",
            choices=[(h, h) for h in headers["web1"]],
            widget=djforms.CheckboxSelectMultiple
        )
        form.fields["join_key_desktop"] = djforms.MultipleChoiceField(
            label="Clés (Desktop) — même nombre et ordre correspondant",
            choices=[(h, h) for h in headers["desktop"]],
            widget=djforms.CheckboxSelectMultiple
        )
        form.fields["join_type"] = djforms.ChoiceField(
            label="Type de jointure",
            choices=[("outer", "outer"), ("inner", "inner"), ("left", "left"), ("right", "right")],
            initial="outer",
            widget=djforms.Select(attrs={"class": "form-select"})
        )

    # 6) POST final -> créer/mettre à jour la configuration
    if request.method == "POST" and request.POST.get("action") != "apply_headers":
        form = ConfigNameForm(request.POST)
        build_dynamic_fields(form)
        if form.is_valid():
            # persist header rows & headers utilisés
            ctx["header_rows"] = {"web1": h_web1, "desktop": h_desk}
            ctx["headers"] = {"web1": list(prev_web1.columns), "desktop": list(prev_desk.columns)}
            request.session["upload_context"] = ctx

            category = get_object_or_404(ConfigCategory, id=ctx["category_id"])
            name = (form.cleaned_data["name"] or "").strip()

            cols_w1 = list(form.cleaned_data["columns_web1"])
            cols_ds = list(form.cleaned_data["columns_desktop"])
            keys_w1 = list(form.cleaned_data["join_key_web1"])
            keys_ds = list(form.cleaned_data["join_key_desktop"])
            join_type = form.cleaned_data["join_type"]

            if not keys_w1 or not keys_ds:
                form.add_error("join_key_web1", "Choisis au moins une clé de chaque côté.")
                form.add_error("join_key_desktop", "Choisis au moins une clé de chaque côté.")
                return render(request, "configs/choose_columns.html", {
                    "form": form,
                    "preview": {
                        "web1": {"columns": list(prev_web1.columns), "rows": prev_web1.values.tolist()},
                        "desktop": {"columns": list(prev_desk.columns), "rows": prev_desk.values.tolist()},
                    },
                })

            if len(keys_w1) != len(keys_ds):
                form.add_error(None, "Le nombre de clés Web1 et Desktop doit être identique (correspondance 1–1).")
                return render(request, "configs/choose_columns.html", {
                    "form": form,
                    "preview": {
                        "web1": {"columns": list(prev_web1.columns), "rows": prev_web1.values.tolist()},
                        "desktop": {"columns": list(prev_desk.columns), "rows": prev_desk.values.tolist()},
                    },
                })

            # validations colonnes existantes
            validate_columns(cols_w1, list(prev_web1.columns))
            validate_columns(cols_ds, list(prev_desk.columns))
            validate_columns(keys_w1, list(prev_web1.columns))
            validate_columns(keys_ds, list(prev_desk.columns))

            # forcer l'inclusion des clés
            cols_w1 = _dedup(cols_w1 + keys_w1)
            cols_ds = _dedup(cols_ds + keys_ds)

            cfg, created = CompareConfig.objects.update_or_create(
                owner=request.user, category=category, name=name,
                defaults={
                    "columns_web1": cols_w1,
                    "columns_desktop": cols_ds,
                    "join_key_web1": keys_w1,
                    "join_key_desktop": keys_ds,
                    "join_type": join_type,
                    "is_active": True,
                },
            )
            request.session["config_id"] = cfg.id
            messages.success(request, f"Configuration « {cfg.name} » {'créée' if created else 'mise à jour'}.")
            return redirect("comparisons:run_with_session")
    else:
        # GET ou POST apply_headers : on construit le form vide/prérempli
        form = ConfigNameForm()
        build_dynamic_fields(form)

    # 7) Contexte template avec aperçus
    return render(request, "configs/choose_columns.html", {
        "form": form,
        "preview": {
            "web1": {"columns": list(prev_web1.columns), "rows": prev_web1.values.tolist()},
            "desktop": {"columns": list(prev_desk.columns), "rows": prev_desk.values.tolist()},
        },
    })
