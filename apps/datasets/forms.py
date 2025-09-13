# apps/datasets/forms.py
from django import forms
from apps.catalogs.models import ConfigCategory

class UploadForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=ConfigCategory.objects.none(),
        label="Catégorie",
        empty_label="Sélectionner…",
    )
    csv_web1 = forms.FileField(label="CSV — Source Web1")
    csv_desktop = forms.FileField(label="CSV — Source Desktop")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ConfigCategory.objects.all().order_by("name")
        self.fields["category"].label_from_instance = lambda o: o.name
