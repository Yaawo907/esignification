"""Passerelle d'expédition SMS — utilisée par l'API interne /api/v1/sms/."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

from notifications.sms import _normaliser_telephone

logger = logging.getLogger(__name__)


def expedier_sms(numero: str, message: str, sender: str = '', provider: str = '') -> bool:
    """
    Envoi réel du SMS selon SMS_GATEWAY_PROVIDER :
    - console : affichage terminal (dev)
    - twilio : Twilio REST
    - webhook : POST vers SMS_GATEWAY_WEBHOOK_URL (votre opérateur / service externe)
    """
    numero = _normaliser_telephone(numero)
    if not numero:
        raise ValueError("Numéro de téléphone invalide.")

    texte = (message or '').strip()[:1600]
    if not texte:
        raise ValueError("Message SMS vide.")

    expediteur = (sender or getattr(settings, 'SMS_SENDER', 'eSignification')).strip()
    provider = (provider or getattr(settings, 'SMS_GATEWAY_PROVIDER', 'console')).lower()

    if provider == 'console':
        logger.info("SMS [gateway:console] → %s : %s", numero, texte)
        print(f"\n[SMS gateway] → {numero}\nExpéditeur : {expediteur}\n{texte}\n")
        return True

    if provider == 'twilio':
        from twilio.rest import Client
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_num = settings.TWILIO_FROM_NUMBER
        if not all([sid, token, from_num]):
            raise ValueError("Configuration Twilio incomplète (TWILIO_*).")
        Client(sid, token).messages.create(body=texte, from_=from_num, to=numero)
        logger.info("SMS [gateway:twilio] envoyé à %s", numero)
        return True

    if provider == 'webhook':
        url = getattr(settings, 'SMS_GATEWAY_WEBHOOK_URL', '').strip()
        if not url:
            raise ValueError("SMS_GATEWAY_WEBHOOK_URL requis pour SMS_GATEWAY_PROVIDER=webhook.")
        payload = json.dumps({
            'to': numero,
            'message': texte,
            'sender': expediteur,
        }).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        webhook_key = getattr(settings, 'SMS_GATEWAY_WEBHOOK_KEY', '').strip()
        if webhook_key:
            headers['Authorization'] = f'Bearer {webhook_key}'
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status >= 400:
                    raise ValueError(f"Webhook SMS HTTP {resp.status}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            raise ValueError(f"Webhook SMS HTTP {exc.code} : {body[:200]}") from exc
        logger.info("SMS [gateway:webhook] transmis à %s via %s", numero, url)
        return True

    if provider == 'smspartner':
        api_key = getattr(settings, 'SMSPARTNER_API_KEY', '').strip()
        if not api_key:
            raise ValueError("SMSPARTNER_API_KEY requis pour SMS_GATEWAY_PROVIDER=smspartner.")
        payload_dict = {
            'apiKey': api_key,
            'phoneNumbers': numero,
            'sender': expediteur[:11],
            'gamme': int(getattr(settings, 'SMSPARTNER_GAMME', 1)),
            'message': texte,
        }
        webhook_url = getattr(settings, 'SMSPARTNER_WEBHOOK_URL', '').strip()
        if webhook_url:
            payload_dict['webhookUrl'] = webhook_url
        payload = json.dumps(payload_dict).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'cache-control': 'no-cache',
        }
        req = urllib.request.Request(
            'https://api.smspartner.fr/v1/send',
            data=payload,
            headers=headers,
            method='POST',
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode('utf-8', errors='replace')
                if resp.status >= 400:
                    raise ValueError(f"SMSPartner HTTP {resp.status} : {body[:200]}")
                if body.strip():
                    try:
                        result = json.loads(body)
                        if isinstance(result, dict) and result.get('success') is False:
                            raise ValueError(result.get('message') or 'Échec SMSPartner')
                    except json.JSONDecodeError:
                        pass
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
            raise ValueError(f"SMSPartner HTTP {exc.code} : {body[:200]}") from exc
        logger.info("SMS [gateway:smspartner] envoyé à %s", numero)
        return True

    raise ValueError(f"SMS_GATEWAY_PROVIDER inconnu : {provider}")
