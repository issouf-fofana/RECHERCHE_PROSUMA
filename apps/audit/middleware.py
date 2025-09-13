from .models import AuditLog
class AuditMiddleware:
    def __init__(self, get_response): self.get_response = get_response
    def __call__(self, request):
        response = self.get_response(request)
        try:
            AuditLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                path=request.path, method=request.method
            )
        except Exception:
            pass
        return response
