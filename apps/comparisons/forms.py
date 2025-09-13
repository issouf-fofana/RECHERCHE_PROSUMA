# apps/comparisons/forms.py
from django import forms
from .models import CompareRun

class RunEditForm(forms.ModelForm):
    class Meta:
        model = CompareRun
        fields = ["title", "notes"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Titre du comparatif"}
            ),
            "notes": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "Notes (optionnel)"}
            ),
        }
