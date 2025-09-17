# apps/datasets/forms.py
from django import forms
from django.core.validators import FileExtensionValidator
from django.db.utils import OperationalError, ProgrammingError

from apps.catalogs.models import ConfigCategory

DEFAULT_CATS = ["BR", "Commande", "Facture"]
OTHER_VALUE = "__other__"

class UploadForm(forms.Form):
    category_choice = forms.ChoiceField(
        label="Catégorie*",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_category_choice"}),
    )
    category_other = forms.CharField(
        label="Nouvelle catégorie",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Saisir une catégorie…",
            "id": "id_category_other",
        }),
    )

    # IMPORTANT: on accepte csv, xls, xlsx
    _allowed = ["csv", "xlsx", "xls"]
    _accept_attr = ".csv,.xlsx,.xls"

    csv_web1 = forms.FileField(
        label="Fichier — Source Web1*",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=_allowed)],
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": _accept_attr}),
    )
    csv_desktop = forms.FileField(
        label="Fichier — Source Desktop*",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=_allowed)],
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": _accept_attr}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        db_names = []
        try:
            db_names = list(ConfigCategory.objects.order_by("name").values_list("name", flat=True))
        except (OperationalError, ProgrammingError):
            db_names = []

        seen, ordered = set(), []
        for n in DEFAULT_CATS + db_names:
            if not n: continue
            key = n.strip(); low = key.lower()
            if low in seen: continue
            seen.add(low); ordered.append((key, key))
        ordered.append((OTHER_VALUE, "Autre…"))
        self.fields["category_choice"].choices = [("", "Sélectionner…")] + ordered

    def get_final_category_name(self) -> str:
        choice = self.cleaned_data.get("category_choice")
        other = self.cleaned_data.get("category_other", "").strip()
        return other if choice == OTHER_VALUE else choice

    def clean(self):
        cleaned = super().clean()
        choice = cleaned.get("category_choice")
        other = (cleaned.get("category_other") or "").strip()
        if choice == OTHER_VALUE and not other:
            self.add_error("category_other", "Veuillez saisir une catégorie.")
        if choice != OTHER_VALUE:
            cleaned["category_other"] = ""
        cleaned["final_category_name"] = other if choice == OTHER_VALUE else choice
        return cleaned
