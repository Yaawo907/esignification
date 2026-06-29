"""Authentification par clé API pour l'endpoint SMS interne."""
from django.conf import settings


def verifier_cle_sms_api(request) -> bool:
    expected = getattr(settings, 'SMS_API_KEY', '').strip()
    if not expected:
        return False

    auth = request.headers.get('Authorization', '') or request.META.get('HTTP_AUTHORIZATION', '')
    if auth.startswith('Bearer '):
        return auth[7:].strip() == expected

    header_name = getattr(settings, 'SMS_API_KEY_HEADER', 'X-API-Key')
    meta_key = 'HTTP_' + header_name.upper().replace('-', '_')
    return (request.headers.get(header_name, '') or request.META.get(meta_key, '')).strip() == expected
