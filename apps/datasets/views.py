# apps/datasets/views.py
import os
import uuid
import pandas as pd  # si non utilisé ailleurs, tu peux enlever
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .forms import UploadForm
from .models import Dataset, FileSource
from .services import analyze_csv, infer_store_from_filename
from apps.catalogs.models import ConfigCategory


def _save_temp(file_obj, prefix):
    """
    Utilitaire facultatif si tu veux persister un fichier temporaire.
    (Non utilisé dans le flux principal car on enregistre via FileField)
    """
    tmp_dir = settings.MEDIA_ROOT / "tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    ext = os.path.splitext(file_obj.name)[1].lower() or ".csv"
    name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    path = tmp_dir / name
    with open(path, "wb+") as dst:
        for chunk in file_obj.chunks():
            dst.write(chunk)
    return str(path)


def _get_or_create_category_by_name(name: str) -> ConfigCategory | None:
    """Retourne la catégorie (créée si besoin) en insensible à la casse."""
    name = (name or "").strip()
    if not name:
        return None
    existing = ConfigCategory.objects.filter(name__iexact=name).first()
    if existing:
        return existing
    return ConfigCategory.objects.create(name=name)


@login_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            # on laisse le template afficher les erreurs du form
            return render(request, "datasets/upload.html", {"form": form})

        # 1) Catégorie finale (gérée par le form.clean)
        final_cat_name = form.cleaned_data.get("final_category_name")
        category = _get_or_create_category_by_name(final_cat_name)
        if not category:
            messages.error(request, "Catégorie invalide.")
            return redirect("datasets:upload")

        # 2) Fichiers
        f1 = form.cleaned_data["csv_web1"]     # InMemoryUploadedFile / TemporaryUploadedFile
        f2 = form.cleaned_data["csv_desktop"]

        # 3) Lecture/analyse rapide (en mémoire), puis reset des curseurs
        try:
            df1, head1, r1, c1 = analyze_csv(f1)
            f1.seek(0)
            df2, head2, r2, c2 = analyze_csv(f2)
            f2.seek(0)
        except Exception as e:
            messages.error(request, f"Erreur lecture CSV : {e}")
            return redirect("datasets:upload")

        # 4) Détection magasin depuis le nom de fichier (ex: 230xsupplierorder_...csv)
        #    infer_store_from_filename doit retourner (code, name) ou (None, None)
        store_code_w1, store_name_w1 = infer_store_from_filename(getattr(f1, "name", ""))
        store_code_dk, store_name_dk = infer_store_from_filename(getattr(f2, "name", ""))

        # 5) Persistance des jeux de données
        #    ⚠️ Si ton modèle Dataset n'a pas store_code/store_name, supprime ces deux attributs.
        ds1 = Dataset.objects.create(
            owner=request.user,
            source=FileSource.WEB1,
            category=category,
            file=f1,            # Django s'occupe de sauvegarder dans MEDIA_ROOT via FileField
            rows=r1,
            columns=c1,
            header=head1,
            store_code=store_code_w1 or "",
            store_name=store_name_w1 or "",
        )
        ds2 = Dataset.objects.create(
            owner=request.user,
            source=FileSource.DESKTOP,
            category=category,
            file=f2,
            rows=r2,
            columns=c2,
            header=head2,
            store_code=store_code_dk or "",
            store_name=store_name_dk or "",
        )

        # 6) Contexte pour l’étape suivante (choix des colonnes & clés)
        request.session["upload_context"] = {
            "category_id": category.id,
            "dataset_web1_id": ds1.id,
            "dataset_desktop_id": ds2.id,
            "headers": {"web1": head1, "desktop": head2},
        }
        return redirect("configs:choose_columns")

    # GET
    form = UploadForm()
    return render(request, "datasets/upload.html", {"form": form})
