# apps/accounts/views.py
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import get_object_or_404, redirect, render

from .forms import UserCreateForm, UserEditForm
from apps.comparisons.models import CompareRun

User = get_user_model()

# ---------------- Admin only helpers ----------------
def _is_admin(u):
    return u.is_authenticated and u.is_staff

# ---------------- Admin views -----------------------
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

@user_passes_test(_is_admin)
def user_toggle_active(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])
    messages.success(request, f"Utilisateur « {user.username} » "
                              f"{'activé' if user.is_active else 'désactivé'}.")
    return redirect("accounts:users_list")

@user_passes_test(_is_admin)
def user_delete(request, user_id):
    u = get_object_or_404(User, id=user_id)
    if request.method == "POST":
        username = u.username
        u.delete()
        messages.success(request, f"Utilisateur « {username} » supprimé.")
        return redirect("accounts:users_list")
    return render(request, "accounts/user_confirm_delete.html", {"user_obj": u})

@user_passes_test(_is_admin)
def user_activity(request, user_id):
    u = get_object_or_404(User, id=user_id)
    runs = (CompareRun.objects
            .filter(config__owner=u)
            .select_related("config", "config__category")
            .order_by("-created_at", "-id")[:200])
    return render(request, "accounts/user_activity.html", {"user_obj": u, "runs": runs})

# ---------------- User views ------------------------
@login_required
def profile(request):
    """Page profil du compte connecté (infos + raccourcis)."""
    recent = (CompareRun.objects
              .filter(config__owner=request.user)
              .select_related("config", "config__category")
              .order_by("-created_at", "-id")[:6])
    return render(request, "accounts/profile.html", {
        "u": request.user,
        "recent_runs": recent,
    })

@login_required
def change_password(request):
    """Changer le mot de passe du compte connecté."""
    if request.method == "POST":
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            # IMPORTANT: garder l’utilisateur connecté après le changement
            update_session_auth_hash(request, user)
            messages.success(request, "Mot de passe mis à jour.")
            return redirect("accounts:profile")
        messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = PasswordChangeForm(user=request.user)
    return render(request, "accounts/password_change.html", {"form": form})

@login_required
def my_activity(request):
    runs = (CompareRun.objects
            .filter(config__owner=request.user)
            .select_related("config", "config__category")
            .order_by("-created_at", "-id")[:200])
    return render(request, "accounts/my_activity.html", {"runs": runs})
