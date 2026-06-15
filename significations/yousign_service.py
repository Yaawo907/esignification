"""
Service Yousign API v3 pour e-Signification Benin.

Architecture :
  - UN SEUL token API au niveau plateforme (gere par l admin).
  - L HUISSIER est le signataire. Yousign lui envoie un lien par email.
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


def creer_demande_signature(signification, pdf_bytes):
    """
    Cree une demande de signature Yousign pour l acte.
    Retourne le signature_request_id.
    Met a jour signification.yousign_signature_request_id et yousign_statut.
    """
    api_key, mode = _get_config()
    huissier = signification.huissier

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

    # 3. Ajouter l huissier comme signataire (OTP email)
    signer = _json_request(
        'POST',
        '/signature_requests/' + sig_req_id + '/signers',
        api_key, mode,
        body={
            'info': {
                'first_name': huissier.prenom,
                'last_name': huissier.nom,
                'email': huissier.user.email,
                'locale': 'fr',
            },
            'signature_level': 'electronic_signature',
            'signature_authentication_mode': 'otp_email',
            'fields': [
                {
                    'type': 'signature',
                    'document_id': doc_id,
                    'page': 1,
                    'x': 360,
                    'y': 680,
                    'width': 120,
                    'height': 60,
                }
            ],
        },
    )
    logger.info("Yousign : signataire ajoute %s", signer.get('id'))

    # 4. Activer -> Yousign envoie email a l huissier
    _json_request('POST', '/signature_requests/' + sig_req_id + '/activate', api_key, mode)
    logger.info("Yousign : signature_request %s activee", sig_req_id)

    signification.yousign_signature_request_id = sig_req_id
    signification.yousign_statut = 'ongoing'
    signification.save(update_fields=['yousign_signature_request_id', 'yousign_statut'])

    return sig_req_id


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


def valider_webhook(payload_bytes, signature_header):
    """Valide la signature HMAC-SHA256 du callback Yousign."""
    from administration.models import ConfigurationPlateforme
    from securite.chiffrement import dechiffrer_texte
    config = ConfigurationPlateforme.get()
    if not config.yousign_webhook_secret_chiffre:
        logger.warning("Webhook Yousign : secret non configure - accepte sans validation.")
        return True
    secret = dechiffrer_texte(config.yousign_webhook_secret_chiffre).encode('utf-8')
    expected = 'sha256=' + hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or '')
