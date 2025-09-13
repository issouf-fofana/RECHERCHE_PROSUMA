# apps/accounts/views.py
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test  # <-- import CORRIGÉ
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UserCreateForm, UserEditForm
from apps.comparisons.models import CompareRun  # pour l'activité

User = get_user_model()


# ---- Admin uniquement (is_staff) ---------------------------------------------

def _is_admin(u):
    return u.is_authenticated and u.is_staff


@user_passes_test(_is_admin)
def users_list(request):
    users = User.objects.all().order_by("-date_joined")
    return render(request, "accounts/users_list.html", {"users": users})


@user_passes_test(_is_admin)
def user_create(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Utilisateur « {user.username} » créé avec succès.")
            return redirect("accounts:users_list")
        # NE PAS rediriger : on ré-affiche le formulaire avec erreurs
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = UserCreateForm(initial={"is_active": True})
    return render(request, "accounts/user_form.html", {"form": form, "mode": "create"})


@user_passes_test(_is_admin)
def user_edit(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Utilisateur « {user.username} » mis à jour.")
            return redirect("accounts:users_list")
        messages.error(request, "Veuillez corriger les erreurs.")
    else:
        form = UserEditForm(instance=user)
    return render(request, "accounts/user_form.html", {"form": form, "mode": "edit", "user_obj": user})


def _is_admin(u): return u.is_authenticated and u.is_staff

@user_passes_test(_is_admin)
def user_toggle_active(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Utilisateur « {user.username} » "
                              f"{'activé' if user.is_active else 'désactivé'}.")
    return redirect("accounts:users_list")

@user_passes_test(lambda u: u.is_staff)
def user_delete(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        username = u.username
        u.delete()
        messages.success(request, f"Utilisateur « {username} » supprimé.")
        return redirect("accounts:users_list")
    return render(request, "accounts/user_confirm_delete.html", {"user_obj": u})


@user_passes_test(lambda u: u.is_staff)
def user_activity(request, user_id):
    """
    Activité d’un utilisateur : comparatifs créés.
    """
    u = get_object_or_404(User, id=user_id)
    runs = (CompareRun.objects
            .filter(config__owner=u)
            .select_related("config", "config__category")
            .order_by("-created_at", "-id")[:200])
    return render(request, "accounts/user_activity.html", {
        "user_obj": u,
        "runs": runs,
    })


# ---- Accès utilisateur (non staff) -------------------------------------------

@login_required
def my_activity(request):
    """
    Activité du compte connecté (pour un user standard).
    """
    runs = (CompareRun.objects
            .filter(config__owner=request.user)
            .select_related("config", "config__category")
            .order_by("-created_at", "-id")[:200])
    return render(request, "accounts/my_activity.html", {"runs": runs})
