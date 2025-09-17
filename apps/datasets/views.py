# apps/datasets/views.py
import os
import uuid
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from .forms import UploadForm
from .models import Dataset, FileSource
from .services import analyze_file, infer_store_from_filename
from apps.catalogs.models import ConfigCategory

def _get_or_create_category_by_name(name: str) -> ConfigCategory | None:
    name = (name or "").strip()
    if not name: return None
    existing = ConfigCategory.objects.filter(name__iexact=name).first()
    return existing or ConfigCategory.objects.create(name=name)

@login_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, "datasets/upload.html", {"form": form})

        final_cat_name = form.cleaned_data.get("final_category_name")
        category = _get_or_create_category_by_name(final_cat_name)
        if not category:
            messages.error(request, "Catégorie invalide.")
            return redirect("datasets:upload")

        f1 = form.cleaned_data["csv_web1"]
        f2 = form.cleaned_data["csv_desktop"]

        # Analyse robuste (CSV ou Excel) + reset des curseurs
        try:
            df1, head1, r1, c1 = analyze_file(f1)
            f1.seek(0)
            df2, head2, r2, c2 = analyze_file(f2)
            f2.seek(0)
        except Exception as e:
            messages.error(request, f"Erreur lecture fichier : {e}")
            return redirect("datasets:upload")

        store_code_w1, store_name_w1 = infer_store_from_filename(getattr(f1, "name", ""))
        store_code_dk, store_name_dk = infer_store_from_filename(getattr(f2, "name", ""))

        ds1 = Dataset.objects.create(
            owner=request.user, source=FileSource.WEB1, category=category,
            file=f1, rows=r1, columns=c1, header=head1,
            store_code=store_code_w1 or "", store_name=store_name_w1 or "",
        )
        ds2 = Dataset.objects.create(
            owner=request.user, source=FileSource.DESKTOP, category=category,
            file=f2, rows=r2, columns=c2, header=head2,
            store_code=store_code_dk or "", store_name=store_name_dk or "",
        )

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
