from django import forms
from .models import CompareConfig

class ConfigNameForm(forms.ModelForm):
    class Meta:
        model = CompareConfig
        fields = ["name"]
