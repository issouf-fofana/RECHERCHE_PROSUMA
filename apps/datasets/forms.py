# apps/datasets/forms.py
from django import forms
from django.core.validators import FileExtensionValidator
from django.db.utils import OperationalError, ProgrammingError

from apps.catalogs.models import ConfigCategory  # pour lire les catégories existantes

DEFAULT_CATS = ["BR", "Commande", "Facture"]
OTHER_VALUE = "__other__"


class UploadForm(forms.Form):
    # Choix de catégorie (rempli dynamiquement en __init__)
    category_choice = forms.ChoiceField(
        label="Catégorie*",
        widget=forms.Select(attrs={
            "class": "form-select",
            "id": "id_category_choice",
        }),
    )

    # Champ libre (sera affiché/masqué au template/JS)
    category_other = forms.CharField(
        label="Nouvelle catégorie",
        required=False,
        widget=forms.TextInput(attrs={
            "class": "form-control",      # pas de d-none ici : on masque le conteneur côté template
            "placeholder": "Saisir une catégorie…",
            "id": "id_category_other",
        }),
    )

    csv_web1 = forms.FileField(
        label="CSV — Source Web1*",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=["csv"])],
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv"}),
    )

    csv_desktop = forms.FileField(
        label="CSV — Source Desktop*",
        required=True,
        validators=[FileExtensionValidator(allowed_extensions=["csv"])],
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".csv"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Construit la liste des catégories :
        # 1) toujours BR/Commande/Facture en premier
        # 2) puis catégories DB (sans doublons, insensible à la casse)
        db_names = []
        try:
            db_names = list(
                ConfigCategory.objects.order_by("name").values_list("name", flat=True)
            )
        except (OperationalError, ProgrammingError):
            # DB pas migrée au moment de l'import : on ignore proprement
            db_names = []

        seen = set()
        ordered = []
        for n in DEFAULT_CATS + db_names:
            if not n:
                continue
            key = n.strip()
            low = key.lower()
            if low in seen:
                continue
            seen.add(low)
            ordered.append((key, key))  # (value, label)

        # Ajoute l'option "Autre…"
        ordered.append((OTHER_VALUE, "Autre…"))

        # Ajoute un placeholder "Sélectionner…"
        self.fields["category_choice"].choices = [("", "Sélectionner…")] + ordered

    # Option utilitaire si tu veux la valeur finale depuis la vue
    def get_final_category_name(self) -> str:
        """
        Retourne le nom de catégorie sélectionné (ou saisi si Autre…).
        À appeler après is_valid().
        """
        choice = self.cleaned_data.get("category_choice")
        other = self.cleaned_data.get("category_other", "").strip()
        if choice == OTHER_VALUE:
            return other
        return choice

    def clean(self):
        cleaned = super().clean()
        choice = cleaned.get("category_choice")
        other = (cleaned.get("category_other") or "").strip()

        # Si "Autre…", le champ libre est obligatoire
        if choice == OTHER_VALUE and not other:
            self.add_error("category_other", "Veuillez saisir une catégorie.")
        # Si une catégorie standard/BDD est choisie, on peut vider le champ libre
        if choice != OTHER_VALUE:
            cleaned["category_other"] = ""

        # Expose la valeur finale (pratique dans la vue)
        cleaned["final_category_name"] = other if choice == OTHER_VALUE else choice
        return cleaned
