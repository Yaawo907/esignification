"""
Service Yousign API v3 pour e-Signification Benin.

Architecture :
  - UN SEUL token API au niveau plateforme (gere par l admin).
  - L HUISSIER est le signataire. Yousign lui envoie un lien par email
    et un code OTP par SMS pour autoriser la signature.
  - Apres signature, le webhook declenche l envoi de l acte signe au justiciable.

Flux :
  1. POST /signature_requests
  2. POST /signature_requests/{id}/documents  (multipart)
  3. POST /signature_requests/{id}/signers
  4. POST /signature_requests/{id}/activate
  Webhook : signature_request.done  -> telecharger PDF signe
"""

import json
import hmac
import hashlib
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

YOUSIGN_BASE_URL = {
    'sandbox': 'https://api-sandbox.yousign.app/v3',
    'production': 'https://api.yousign.app/v3',
}


def message_erreur_yousign_api(detail: str) -> str:
    """Traduit une réponse d'erreur Yousign en message utilisateur (français)."""
    err = (detail or '').lower()
    if 'sandbox mode' in err and 'email' in err and 'organization' in err:
        return (
            "Yousign (sandbox) : l'email de l'huissier doit appartenir à votre organisation "
            "Yousign. Pour les tests, utilisez l'email du compte Yousign, ou contactez "
            "le support Yousign pour lever cette restriction."
        )
    if 'phone_number' in err:
        return (
            "Yousign a refusé le numéro de téléphone. "
            "Format attendu : +22901XXXXXXXX (ex. +2290166004617)."
        )
    return ''


def _get_config():
    """Retourne (api_key, mode) ou leve ValueError."""
    from administration.models import ConfigurationPlateforme
    from securite.chiffrement import dechiffrer_texte
    config = ConfigurationPlateforme.get()
    if not config.yousign_active:
        raise ValueError("Yousign non active.")
    if not config.yousign_api_key_chiffre:
        raise ValueError("Cle API Yousign non configuree.")
    return dechiffrer_texte(config.yousign_api_key_chiffre), config.yousign_mode


def _json_request(method, path, api_key, mode, body=None):
    """Requete JSON vers Yousign API v3."""
    url = YOUSIGN_BASE_URL[mode] + path
    headers = {
        'Authorization': 'Bearer ' + api_key,
        'Accept': 'application/json',
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        logger.error("Yousign API %s %s -> %s : %s", method, path, e.code, detail)
        raise RuntimeError("Yousign erreur " + str(e.code) + ": " + detail) from e


def _upload_document(api_key, mode, sig_req_id, pdf_bytes, filename):
    """
    POST /signature_requests/{id}/documents  multipart/form-data
    Champs : nature=signable_document  +  file (PDF)
    """
    url = YOUSIGN_BASE_URL[mode] + '/signature_requests/' + sig_req_id + '/documents'
    boundary = b'----YousignBnd99'

    def field_part(name, value):
        return (
            b'--' + boundary + b'\r\n'
            b'Content-Disposition: form-data; name="' + name.encode() + b'"\r\n\r\n'
            + value.encode() + b'\r\n'
        )

    def file_part(fname, data):
        return (
            b'--' + boundary + b'\r\n'
            b'Content-Disposition: form-data; name="file"; filename="' + fname.encode() + b'"\r\n'
            b'Content-Type: application/pdf\r\n\r\n'
            + data + b'\r\n'
        )

    body = (
        field_part('nature', 'signable_document')
        + file_part(filename, pdf_bytes)
        + b'--' + boundary + b'--\r\n'
    )
    headers = {
        'Authorization': 'Bearer ' + api_key,
        'Accept': 'application/json',
        'Content-Type': 'multipart/form-data; boundary=' + boundary.decode(),
    }
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        logger.error("Yousign upload -> %s : %s", e.code, detail)
        raise RuntimeError("Yousign upload erreur " + str(e.code) + ": " + detail) from e


def _download_bytes(api_key, mode, path):
    """Telecharge des bytes bruts (PDF signe)."""
    url = YOUSIGN_BASE_URL[mode] + path
    req = urllib.request.Request(url, headers={
        'Authorization': 'Bearer ' + api_key,
        'Accept': 'application/pdf',
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', errors='replace')
        logger.error("Yousign download %s -> %s : %s", path, e.code, detail)
        raise RuntimeError("Yousign download erreur " + str(e.code) + ": " + detail) from e


def _expiration_date():
    """7 jours - format YYYY-MM-DD attendu par Yousign v3."""
    from datetime import datetime, timedelta, timezone
    return (datetime.now(tz=timezone.utc) + timedelta(days=7)).strftime('%Y-%m-%d')


def creer_demande_signature(signification, pdf_bytes, placement=None):
    """
    Cree une demande de signature Yousign pour l acte.
    Retourne le signature_request_id.
    Met a jour signification.yousign_signature_request_id et yousign_statut.

    placement : dict optionnel {page, x, y, width, height} en points PDF
    (origine haut-gauche, comme l API Yousign v3).
    """
    from .yousign_placement import (
        YOUSIGN_SIG_WIDTH_DEFAULT,
        YOUSIGN_SIG_HEIGHT_DEFAULT,
    )

    if placement is None:
        placement = {
            'page': 1,
            'x': 360,
            'y': 680,
            'width': YOUSIGN_SIG_WIDTH_DEFAULT,
            'height': YOUSIGN_SIG_HEIGHT_DEFAULT,
        }
    from notifications.sms import normaliser_telephone_yousign

    api_key, mode = _get_config()
    huissier = signification.huissier
    try:
        phone_number = normaliser_telephone_yousign(huissier.telephone)
    except ValueError:
        raise
    except Exception:
        raise ValueError(
            "Numéro de téléphone huissier invalide pour l'OTP SMS Yousign."
        ) from None

    # 1. Creer la signature_request
    sig_req = _json_request('POST', '/signature_requests', api_key, mode, body={
        'name': 'Signification ' + signification.reference,
        'delivery_mode': 'email',
        'ordered_signers': False,
        'expiration_date': _expiration_date(),
        'timezone': 'Africa/Porto-Novo',
        'reminder_settings': {
            'interval_in_days': 1,
            'max_occurrences': 3,
        },
    })
    sig_req_id = sig_req['id']
    logger.info("Yousign : signature_request creee %s pour %s", sig_req_id, signification.reference)

    # 2. Uploader le PDF
    doc = _upload_document(
        api_key, mode, sig_req_id,
        pdf_bytes,
        'acte_' + signification.reference + '.pdf',
    )
    doc_id = doc['id']
    logger.info("Yousign : document uploade %s", doc_id)

    # 3. Ajouter l huissier comme signataire (lien email + OTP SMS)
    signer = _json_request(
        'POST',
        '/signature_requests/' + sig_req_id + '/signers',
        api_key, mode,
        body={
            'info': {
                'first_name': huissier.prenom,
                'last_name': huissier.nom,
                'email': huissier.user.email,
                'phone_number': phone_number,
                'locale': 'fr',
            },
            'signature_level': 'electronic_signature',
            'signature_authentication_mode': 'otp_sms',
            'fields': [
                {
                    'type': 'signature',
                    'document_id': doc_id,
                    'page': placement['page'],
                    'x': placement['x'],
                    'y': placement['y'],
                    'width': placement['width'],
                    'height': placement['height'],
                }
            ],
        },
    )
    logger.info("Yousign : signataire ajoute %s", signer.get('id'))

    # 4. Activer -> Yousign envoie le lien par email ; l OTP arrive par SMS a la signature
    _json_request('POST', '/signature_requests/' + sig_req_id + '/activate', api_key, mode)
    logger.info("Yousign : signature_request %s activee", sig_req_id)

    signification.yousign_signature_request_id = sig_req_id
    signification.yousign_signer_id = signer.get('id', '')
    signification.yousign_statut = 'ongoing'
    signification.save(update_fields=['yousign_signature_request_id', 'yousign_signer_id', 'yousign_statut'])

    return sig_req_id


def recuperer_statut_yousign(sig_req_id: str) -> str:
    """Interroge Yousign pour le statut d'une signature_request."""
    api_key, mode = _get_config()
    data = _json_request('GET', '/signature_requests/' + sig_req_id, api_key, mode)
    return data.get('status', '')


def telecharger_document_signe(sig_req_id, doc_id=None):
    """Telecharge le PDF signe. Si doc_id absent, prend le premier document."""
    api_key, mode = _get_config()
    if not doc_id:
        req_data = _json_request('GET', '/signature_requests/' + sig_req_id, api_key, mode)
        docs = req_data.get('documents', [])
        if not docs:
            raise RuntimeError("Aucun document dans la signature_request.")
        doc_id = docs[0]['id']
    return _download_bytes(
        api_key, mode,
        '/signature_requests/' + sig_req_id + '/documents/' + doc_id + '/download',
    )


def recuperer_signataire_id(sig_req_id, signer_id=None):
    """Retourne l'ID du premier signataire si signer_id absent."""
    if signer_id:
        return signer_id
    api_key, mode = _get_config()
    data = _json_request('GET', '/signature_requests/' + sig_req_id + '/signers', api_key, mode)
    signers = data if isinstance(data, list) else data.get('data', [])
    if not signers:
        raise RuntimeError("Aucun signataire dans la signature_request.")
    return signers[0]['id']


def telecharger_audit_trail(sig_req_id, signer_id=None):
    """Telecharge le dossier de preuve Yousign (audit trail PDF) du signataire."""
    api_key, mode = _get_config()
    sid = recuperer_signataire_id(sig_req_id, signer_id)
    return _download_bytes(
        api_key, mode,
        '/signature_requests/' + sig_req_id + '/signers/' + sid + '/audit_trails/download',
    )


def _secrets_webhook():
    """Secrets HMAC valides (base admin + variables d'environnement)."""
    from django.conf import settings
    from administration.models import ConfigurationPlateforme
    from securite.chiffrement import dechiffrer_texte

    secrets = []
    for raw in (
        getattr(settings, 'YOUSIGN_WEBHOOK_SECRET', ''),
        getattr(settings, 'WEBHOOK_SECRET', ''),
    ):
        s = (raw or '').strip()
        if not s:
            continue
        if s.startswith('http://') or s.startswith('https://'):
            logger.warning(
                "Secret webhook Yousign invalide (ressemble à une URL, pas à une clé HMAC) : %s",
                s[:48],
            )
            continue
        if s not in secrets:
            secrets.append(s)

    if getattr(settings, 'DEBUG', False) and secrets:
        return secrets

    try:
        config = ConfigurationPlateforme.get()
        if config.yousign_webhook_secret_chiffre:
            db_secret = dechiffrer_texte(config.yousign_webhook_secret_chiffre).strip()
            if db_secret and db_secret not in secrets:
                if db_secret.startswith('http://') or db_secret.startswith('https://'):
                    logger.warning(
                        "Secret webhook Yousign en base invalide (URL au lieu d'une clé HMAC)."
                    )
                else:
                    secrets.append(db_secret)
    except Exception as exc:
        logger.warning("Webhook Yousign : lecture secret base — %s", exc)

    return secrets


def _get_webhook_secret():
    """Compatibilité — retourne le premier secret configuré."""
    secrets = _secrets_webhook()
    return secrets[0] if secrets else ''


def valider_webhook(payload_bytes, signature_header):
    """Valide la signature HMAC-SHA256 du callback Yousign."""
    secrets = _secrets_webhook()
    if not secrets:
        logger.warning("Webhook Yousign : secret non configure - accepte sans validation.")
        return True
    header = signature_header or ''
    for secret in secrets:
        expected = 'sha256=' + hmac.new(
            secret.encode('utf-8'), payload_bytes, hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(expected, header):
            return True
    logger.warning(
        "Webhook Yousign : signature invalide (header present=%s, secrets testes=%d)",
        bool(header), len(secrets),
    )
    return False


def extraire_signature_request_id(payload: dict) -> str:
    """Extrait l'ID signature_request depuis le payload webhook Yousign v3."""
    data = payload.get('data') or {}
    if not isinstance(data, dict):
        return ''
    sig_req = data.get('signature_request')
    if isinstance(sig_req, dict):
        return sig_req.get('id', '') or ''
    if isinstance(sig_req, str):
        return sig_req
    return data.get('signature_request_id', '') or ''
