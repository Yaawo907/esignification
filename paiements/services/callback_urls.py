"""URLs de callback Kkiapay (Render, domaine personnalisé, local)."""
from urllib.parse import urlparse

from django.conf import settings


def _is_local_host(hostname: str) -> bool:
    return (hostname or '').lower() in {'127.0.0.1', 'localhost'}


def _ensure_callback_path(path: str) -> str:
    if not path or path == '/':
        return '/paiements/callback/kkiapay/'
    if not path.startswith('/'):
        return f'/{path}'
    return path


def get_callback_url_kkiapay(request=None) -> str:
    """
    URL complète du callback Kkiapay pour le widget et le dashboard Kkiapay.

    Si KKIAPAY_CALLBACK_URL = https://esignification.onrender.com (sans chemin),
    le chemin /paiements/callback/kkiapay/ est ajouté automatiquement.
    """
    configured = (getattr(settings, 'KKIAPAY_CALLBACK_URL', '') or '').strip()
    if configured:
        if configured.startswith('http'):
            parsed = urlparse(configured)
            path = _ensure_callback_path(parsed.path or '')
            if not parsed.path or parsed.path == '/':
                scheme = parsed.scheme or 'https'
                netloc = parsed.netloc or (parsed.hostname or '')
                if _is_local_host(parsed.hostname or '') and request:
                    host = request.get_host()
                    if host:
                        return f'{request.scheme}://{host}{path}'
                return f'{scheme}://{netloc}{path}'
            return configured
        scheme = 'https' if not settings.DEBUG else 'http'
        base = configured.rstrip('/')
        return f'{scheme}://{base}/paiements/callback/kkiapay/'

    if request:
        from django.urls import reverse
        return request.build_absolute_uri(reverse('paiements:callback_kkiapay'))

    site = (getattr(settings, 'SITE_URL', '') or '').strip().rstrip('/')
    if site:
        return f'{site}/paiements/callback/kkiapay/'
    return 'http://127.0.0.1:8000/paiements/callback/kkiapay/'
