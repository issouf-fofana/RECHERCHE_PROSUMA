from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirmation du mot de passe",
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ["username", "email", "is_staff", "is_active"]
        labels = {
            "username": "Nom d’utilisateur",
            "email": "Email",
            "is_staff": "Administrateur",
            "is_active": "Actif",
        }
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control", "placeholder": "ex: y.Fofana"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "ex: fofana@alien.al"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input", "checked": True}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1") or ""
        p2 = cleaned.get("password2") or ""
        if not p1:
            self.add_error("password1", "Mot de passe requis.")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Les mots de passe ne correspondent pas.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        # IMPORTANT: hash du mot de passe
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "is_staff", "is_active"]
        labels = {
            "email": "Email",
            "is_staff": "Administrateur",
            "is_active": "Actif",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
