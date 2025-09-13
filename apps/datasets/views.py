import os, uuid, pandas as pd
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .forms import UploadForm
from .models import Dataset, FileSource
from .services import analyze_csv

def _save_temp(file_obj, prefix):
    tmp_dir = settings.MEDIA_ROOT / "tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    ext = os.path.splitext(file_obj.name)[1].lower() or ".csv"
    name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    path = tmp_dir / name
    with open(path, "wb+") as dst:
        for chunk in file_obj.chunks(): dst.write(chunk)
    return str(path)

@login_required
def upload(request):
    if request.method == "POST":
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            category = form.cleaned_data["category"]
            f1 = form.cleaned_data["csv_web1"]
            f2 = form.cleaned_data["csv_desktop"]

            # analyse en mémoire
            try:
                df1, head1, r1, c1 = analyze_csv(f1)
                f1.seek(0)
                df2, head2, r2, c2 = analyze_csv(f2)
                f2.seek(0)
            except Exception as e:
                messages.error(request, f"Erreur lecture CSV : {e}")
                return redirect("datasets:upload")

            # persister fichiers
            ds1 = Dataset.objects.create(
                owner=request.user, source=FileSource.WEB1, category=category,
                file=f1, rows=r1, columns=c1, header=head1
            )
            ds2 = Dataset.objects.create(
                owner=request.user, source=FileSource.DESKTOP, category=category,
                file=f2, rows=r2, columns=c2, header=head2
            )

            # garder en session pour l’étape suivante
            request.session["upload_context"] = {
                "category_id": category.id,
                "dataset_web1_id": ds1.id,
                "dataset_desktop_id": ds2.id,
                "headers": {"web1": head1, "desktop": head2},
            }
            return redirect("configs:choose_columns")
    else:
        form = UploadForm()
    return render(request, "datasets/upload.html", {"form": form})
