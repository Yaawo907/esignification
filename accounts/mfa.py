"""Helpers MFA — email, SMS, TOTP (Google Authenticator)."""
import base64
import io
import logging
import re
from datetime import timedelta

import pyotp
import qrcode
from django.utils import timezone
from django.utils.crypto import get_random_string

from accounts.models import User

logger = logging.getLogger(__name__)


def telephone_utilisateur(user) -> str:
    try:
        if user.role == User.HUISSIER:
            return (user.profil_huissier.telephone or '').strip()
        if user.role == User.CLERC:
            c = user.profil_clerc
            return (c.telephone or c.huissier.telephone or '').strip()
        if user.role == User.JUSTICIABLE:
            return (user.profil_justiciable.telephone or '').strip()
    except Exception:
        pass
    return ''


def generer_code_mfa() -> str:
    return get_random_string(6, '0123456789')


def envoyer_code_mfa(user) -> bool:
    """Génère et envoie un code MFA selon la méthode configurée."""
    code = generer_code_mfa()
    user.mfa_code = code
    user.mfa_code_expiry = timezone.now() + timedelta(minutes=10)
    user.save(update_fields=['mfa_code', 'mfa_code_expiry'])

    if user.mfa_methode == User.MFA_EMAIL:
        from notifications.service import envoyer_email
        corps = f"""
        <div style="font-family:Arial,sans-serif;padding:24px;">
          <h2 style="color:#1a3c6e;">Code de vérification</h2>
          <p>Votre code de connexion e-Signification est :</p>
          <p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1a3c6e;">{code}</p>
          <p style="color:#888;">Ce code expire dans 10 minutes. Ne le partagez avec personne.</p>
        </div>"""
        corps_texte = f"Votre code e-Signification : {code}\nValide 10 minutes."
        envoyer_email(user.email, "Code de vérification — e-Signification Bénin", corps, corps_texte)
        return True

    if user.mfa_methode == User.MFA_OTP:
        from accounts.mfa_profil import sms_mfa_disponible
        if not sms_mfa_disponible():
            logger.warning("MFA SMS désactivé — envoi par email pour %s", user.email)
            from notifications.service import envoyer_email
            corps = f"""
            <div style="font-family:Arial,sans-serif;padding:24px;">
              <h2 style="color:#1a3c6e;">Code de vérification</h2>
              <p>Votre code de connexion e-Signification est :</p>
              <p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1a3c6e;">{code}</p>
              <p style="color:#888;">Ce code expire dans 10 minutes. Ne le partagez avec personne.</p>
            </div>"""
            corps_texte = f"Votre code e-Signification : {code}\nValide 10 minutes."
            envoyer_email(user.email, "Code de vérification — e-Signification Bénin", corps, corps_texte)
            return True
        tel = telephone_utilisateur(user)
        if not tel:
            logger.error("MFA SMS : aucun téléphone pour %s", user.email)
            return False
        from notifications.sms import envoyer_sms
        msg = f"e-Signification : votre code de connexion est {code}. Valide 10 min."
        envoyer_sms(tel, msg)
        return True

    return False


def _normaliser_code(code: str) -> str:
    return re.sub(r'\D', '', (code or '').strip())


def verifier_code_mfa(user, code: str) -> bool:
    code = _normaliser_code(code)
    if len(code) != 6:
        return False

    user.refresh_from_db(fields=['mfa_methode', 'totp_secret', 'mfa_code', 'mfa_code_expiry'])

    if user.mfa_methode == User.MFA_TOTP:
        if not user.totp_secret:
            return False
        return pyotp.TOTP(user.totp_secret).verify(code, valid_window=2)

    if (user.mfa_code == code
            and user.mfa_code_expiry
            and timezone.now() < user.mfa_code_expiry):
        user.mfa_code = ''
        user.mfa_code_expiry = None
        user.save(update_fields=['mfa_code', 'mfa_code_expiry'])
        return True
    return False


def generer_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name='eSignification',
    )


def qr_code_data_uri(provisioning_uri: str) -> str:
    img = qrcode.make(provisioning_uri, box_size=4, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode('ascii')
    return f'data:image/png;base64,{b64}'


def verifier_totp_setup(secret: str, code: str) -> bool:
    code = _normaliser_code(code)
    if len(code) != 6 or not secret:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=2)
