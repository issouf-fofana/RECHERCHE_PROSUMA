from django.contrib.auth.decorators import login_required
from django.http import HttpResponse

@login_required
def me(request):
    return HttpResponse(f"Hello {request.user.username}")
