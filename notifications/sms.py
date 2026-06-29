"""Envoi SMS — console (dev), Twilio ou API HTTP personnalisée."""
import json
import logging
import re
import threading
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

_INDICATIF_BENIN = '229'
_E164_RE = re.compile(r'^\+[1-9]\d{6,14}$')
# Depuis nov. 2024 : 10 chiffres nationaux (01 + ancien numéro à 8 chiffres)
_BJ_NATIONAL_10_RE = re.compile(r'^01[2-9]\d{7}$')
# Ancien format local (8 chiffres) — converti automatiquement en 01XXXXXXXX
_BJ_LEGACY_8_RE = re.compile(r'^[2-9]\d{7}$')
_MSG_FORMAT_BENIN = (
    "Format attendu : 01XXXXXXXX (ex. 0166004617) ou international +2290166004617."
)


def _vers_national_benin_10(digits: str) -> str:
    """Retourne le numéro national à 10 chiffres (01XXXXXXXX) ou une chaîne vide."""
    if _BJ_NATIONAL_10_RE.match(digits):
        return digits
    if _BJ_LEGACY_8_RE.match(digits):
        return '01' + digits
    return ''


def _normaliser_telephone_benin(digits: str) -> str:
    """Convertit des chiffres locaux/internationaux Bénin vers +22901XXXXXXXX."""
    indicatif = _INDICATIF_BENIN

    while digits.startswith(indicatif + indicatif):
        digits = digits[len(indicatif):]

    if digits.startswith(indicatif):
        national = digits[len(indicatif):]
        national_10 = _vers_national_benin_10(national)
        if national_10:
            return '+' + indicatif + national_10
        return ''

    national_10 = _vers_national_benin_10(digits)
    if national_10:
        return '+' + indicatif + national_10

    return ''


def _chiffres_seuls(numero: str) -> str:
    return re.sub(r'\D', '', (numero or '').strip())


def _normaliser_telephone(numero: str) -> str:
    """Format E.164 — Bénin (+229) par défaut, autres indicatifs conservés."""
    raw = (numero or '').strip()
    if not raw:
        return ''

    digits = _chiffres_seuls(raw)
    if not digits:
        return ''

    if digits.startswith('00'):
        digits = digits[2:]

    benin = _normaliser_telephone_benin(digits)
    if benin:
        return benin

    # Autre pays : indicatif international déjà présent (ex. 33…, 1…)
    if len(digits) >= 10:
        candidate = '+' + digits
        if _E164_RE.match(candidate):
            return candidate

    return ''


def telephone_e164_valide(numero: str) -> bool:
    return bool(numero and _E164_RE.match(numero))


def normaliser_telephone_yousign(numero: str) -> str:
    """
    Normalise et valide un numéro pour Yousign (OTP SMS).
    Lève ValueError si le format E.164 est invalide.
    """
    normalise = _normaliser_telephone(numero)
    if not normalise or not telephone_e164_valide(normalise):
        raise ValueError(
            "Numéro de téléphone invalide pour Yousign. " + _MSG_FORMAT_BENIN
        )
    return normalise


def _envoyer_sms_sync(numero: str, message: str) -> bool:
    numero = _normaliser_telephone(numero)
    if not numero:
        raise ValueError("Numéro de téléphone invalide.")

    backend = getattr(settings, 'SMS_BACKEND', 'console')

    if backend == 'custom':
        return _envoyer_sms_custom(numero, message)

    if backend in ('console', 'twilio'):
        from notifications.sms_gateway import expedier_sms
        sender = getattr(settings, 'SMS_SENDER', 'eSignification').strip() or 'eSignification'
        return expedier_sms(numero, message, sender, provider=backend)

    raise ValueError(f"SMS_BACKEND inconnu : {backend}")


def _envoyer_sms_custom(numero: str, message: str) -> bool:
    """
    Appelle votre API SMS (POST JSON).
    Corps envoyé : {"to": "+229...", "message": "...", "sender": "..."}
    En-tête : Authorization: Bearer <SMS_API_KEY> (si SMS_API_KEY est défini)
    """
    url = getattr(settings, 'SMS_API_URL', '').strip()
    if not url:
        raise ValueError("SMS_API_URL est obligatoire quand SMS_BACKEND=custom.")
    # Django APPEND_SLASH : POST sans slash final provoque une erreur 500
    if '?' not in url and not url.endswith('/'):
        url += '/'

    api_key = getattr(settings, 'SMS_API_KEY', '').strip()
    sender = getattr(settings, 'SMS_SENDER', 'eSignification').strip() or 'eSignification'

    payload = {
        'to': numero,
        'message': message[:1600],
        'sender': sender,
    }
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if api_key:
        auth_style = getattr(settings, 'SMS_API_AUTH_STYLE', 'bearer').lower()
        if auth_style == 'header':
            headers[getattr(settings, 'SMS_API_KEY_HEADER', 'X-API-Key')] = api_key
        else:
            headers['Authorization'] = f'Bearer {api_key}'

    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=getattr(settings, 'SMS_API_TIMEOUT', 30)) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            if resp.status >= 400:
                raise ValueError(f"API SMS HTTP {resp.status} : {body[:200]}")
            if body.strip():
                try:
                    result = json.loads(body)
                    if isinstance(result, dict) and result.get('success') is False:
                        raise ValueError(result.get('error') or result.get('message') or 'Échec API SMS')
                except json.JSONDecodeError:
                    pass
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
        raise ValueError(f"API SMS HTTP {exc.code} : {err_body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"API SMS injoignable : {exc.reason}") from exc

    logger.info("SMS custom envoyé à %s via %s", numero, url)
    return True


def envoyer_sms(numero: str, message: str) -> bool:
    """Envoi asynchrone (non bloquant)."""
    def _run():
        try:
            _envoyer_sms_sync(numero, message)
        except Exception as exc:
            logger.error("Erreur envoi SMS vers %s : %s", numero, exc)

    threading.Thread(target=_run, daemon=True).start()
    return True
