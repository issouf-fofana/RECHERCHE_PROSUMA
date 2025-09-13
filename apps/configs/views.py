from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django import forms as djforms

from .models import CompareConfig
from .forms import ConfigNameForm
from .services import validate_columns
from apps.catalogs.models import ConfigCategory

def _dedup(seq):
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            out.append(x); seen.add(x)
    return out

@login_required
def choose_columns(request):
    ctx = request.session.get("upload_context")
    if not ctx:
        messages.error(request, "Commence par charger deux CSV.")
        return redirect("datasets:upload")

    headers = ctx["headers"]

    # Helper pour construire les champs dynamiques
    def build_dynamic_fields(form):
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
        # ⬇️ clés composites (plusieurs colonnes possibles)
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
            choices=[("outer","outer"),("inner","inner"),("left","left"),("right","right")],
            initial="outer"
        )

    if request.method == "POST":
        form = ConfigNameForm(request.POST)
        build_dynamic_fields(form)

        if form.is_valid():
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
                return render(request, "configs/choose_columns.html", {"form": form})

            if len(keys_w1) != len(keys_ds):
                form.add_error(None, "Le nombre de clés Web1 et Desktop doit être identique (correspondance 1–1).")
                return render(request, "configs/choose_columns.html", {"form": form})

            # validations colonnes existantes
            validate_columns(cols_w1, headers["web1"])
            validate_columns(cols_ds, headers["desktop"])
            validate_columns(keys_w1, headers["web1"])
            validate_columns(keys_ds, headers["desktop"])

            # forcer l'inclusion des clés dans les colonnes sélectionnées
            cols_w1 = _dedup(cols_w1 + keys_w1)
            cols_ds = _dedup(cols_ds + keys_ds)

            cfg, created = CompareConfig.objects.update_or_create(
                owner=request.user, category=category, name=name,
                defaults={
                    "columns_web1": cols_w1,
                    "columns_desktop": cols_ds,
                    "join_key_web1": keys_w1,         # ⬅️ listes ordonnées
                    "join_key_desktop": keys_ds,      # ⬅️ listes ordonnées
                    "join_type": join_type,
                    "is_active": True,
                },
            )
            request.session["config_id"] = cfg.id
            messages.success(request, f"Configuration « {cfg.name} » {'créée' if created else 'mise à jour'}.")
            return redirect("comparisons:run_with_session")
    else:
        form = ConfigNameForm()
        build_dynamic_fields(form)

    return render(request, "configs/choose_columns.html", {"form": form})
