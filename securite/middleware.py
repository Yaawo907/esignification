from administration.models import PisteAudit


class AuditMiddleware:
    """Enregistre automatiquement certaines actions dans la piste d'audit"""
    ACTIONS_A_TRACER = ['/connexion/', '/deconnexion/', '/admin/']

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if request.method == 'POST' and any(request.path.startswith(a) for a in self.ACTIONS_A_TRACER):
                user = request.user if request.user.is_authenticated else None
                PisteAudit.objects.create(
                    user=user,
                    user_email=user.email if user else '',
                    action=f"POST {request.path}",
                    ip_address=self._get_ip(request),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
                )
        except Exception:
            pass
        return response

    def _get_ip(self, request):
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded:
            return x_forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class SecuriteHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.http import HttpResponseBase
        response = self.get_response(request)
        if isinstance(response, HttpResponseBase):
            response['X-Content-Type-Options'] = 'nosniff'
            response['X-Frame-Options'] = 'DENY'
            response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
            response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        return response
