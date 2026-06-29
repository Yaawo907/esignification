"""Gestion MFA depuis les pages profil (huissier, justiciable, admin)."""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect

from accounts.models import User


def sms_mfa_disponible() -> bool:
    return getattr(settings, 'MFA_SMS_ENABLED', False)


def methodes_mfa_autorisees() -> set:
    methodes = {User.MFA_EMAIL, User.MFA_TOTP}
    if sms_mfa_disponible():
        methodes.add(User.MFA_OTP)
    return methodes


def options_mfa_ui(user, telephone: str = '') -> list:
    """Options MFA pour l'interface (SMS grisé si désactivé)."""
    tel = (telephone or '').strip()
    options = []
    for val, label in User.MFA_CHOICES:
        opt = {
            'val': val,
            'label': label,
            'disabled': False,
            'badge': '',
            'desc': '',
        }
        if val == User.MFA_EMAIL:
            opt['desc'] = f"Code envoyé à {user.email}"
        elif val == User.MFA_OTP:
            if not sms_mfa_disponible():
                opt['disabled'] = True
                opt['badge'] = 'Bientôt disponible'
                opt['desc'] = "Authentification par SMS — fonctionnalité à venir."
            elif not tel:
                opt['desc'] = "SMS — renseignez votre numéro de téléphone dans le profil."
            else:
                opt['desc'] = f"SMS au {tel}"
        elif val == User.MFA_TOTP:
            opt['desc'] = "Google Authenticator, Microsoft Authenticator, etc."
        options.append(opt)
    return options


def contexte_mfa_profil(user, session) -> dict:
    from accounts.mfa import totp_provisioning_uri, qr_code_data_uri, telephone_utilisateur

    telephone = telephone_utilisateur(user)
    totp_en_attente = (
        user.mfa_methode != User.MFA_TOTP
        and bool(user.totp_secret)
    ) or bool(session.get('totp_pending_secret'))

    secret_pending = session.get('totp_pending_secret') or (
        user.totp_secret if totp_en_attente and user.mfa_methode != User.MFA_TOTP else ''
    )

    totp_setup = None
    if secret_pending:
        uri = totp_provisioning_uri(user, secret_pending)
        totp_setup = {
            'secret': secret_pending,
            'qr_data_uri': qr_code_data_uri(uri),
            'uri': uri,
        }

    return {
        'mfa_methode': user.mfa_methode,
        'mfa_options': options_mfa_ui(user, telephone),
        'totp_actif': bool(user.totp_secret and user.mfa_methode == User.MFA_TOTP),
        'totp_setup': totp_setup,
        'sms_mfa_disponible': sms_mfa_disponible(),
    }


def traiter_action_mfa_profil(request, user, redirect_to: str, telephone: str = ''):
    """
    Traite les actions POST mfa_methode, totp_confirmer, totp_annuler.
    Retourne une HttpResponseRedirect si une action MFA a été traitée, sinon None.
    """
    from securite.audit import journaliser
    from accounts.mfa import generer_totp_secret, verifier_totp_setup

    action = request.POST.get('action', '')
    if action not in ('mfa_methode', 'totp_confirmer', 'totp_annuler'):
        return None

    if action == 'mfa_methode':
        nouvelle = request.POST.get('mfa_methode', User.MFA_EMAIL)
        autorisees = methodes_mfa_autorisees()
        if nouvelle not in autorisees:
            if nouvelle == User.MFA_OTP:
                messages.error(
                    request,
                    "L'authentification par SMS n'est pas encore disponible. Bientôt disponible.",
                )
            else:
                messages.error(request, "Méthode de vérification invalide.")
            return redirect(redirect_to)
        if nouvelle == User.MFA_OTP and not (telephone or '').strip():
            messages.error(
                request,
                "Renseignez votre numéro de téléphone dans le profil avant d'activer le SMS.",
            )
            return redirect(redirect_to)
        if nouvelle == User.MFA_TOTP:
            if user.mfa_methode == User.MFA_TOTP and user.totp_secret:
                messages.info(request, "Google Authenticator est déjà actif.")
                return redirect(redirect_to)
            secret = generer_totp_secret()
            user.totp_secret = secret
            user.save(update_fields=['totp_secret'])
            request.session['totp_pending_secret'] = secret
            request.session.modified = True
            messages.info(
                request,
                "Scannez le QR code, puis saisissez le code à 6 chiffres pour finaliser l'activation.",
            )
            return redirect(redirect_to)

        user.mfa_methode = nouvelle
        if nouvelle != User.MFA_TOTP:
            user.totp_secret = ''
        user.save(update_fields=['mfa_methode', 'totp_secret'])
        request.session.pop('totp_pending_secret', None)
        journaliser(user, 'mfa_methode_modifiee', description=nouvelle, request=request)
        libelles = dict(User.MFA_CHOICES)
        messages.success(request, f"Vérification configurée : {libelles.get(nouvelle, nouvelle)}.")
        return redirect(redirect_to)

    if action == 'totp_confirmer':
        secret = request.session.get('totp_pending_secret') or user.totp_secret
        code = request.POST.get('totp_code', '').strip()
        if not secret:
            messages.error(request, "Configuration expirée. Recommencez.")
        elif not code:
            messages.error(request, "Entrez le code à 6 chiffres de l'application.")
        elif verifier_totp_setup(secret, code):
            User.objects.filter(pk=user.pk).update(
                mfa_methode=User.MFA_TOTP,
                totp_secret=secret,
                mfa_code='',
                mfa_code_expiry=None,
            )
            request.session.pop('totp_pending_secret', None)
            journaliser(user, 'mfa_totp_active', request=request)
            messages.success(
                request,
                "Google Authenticator activé. À la prochaine connexion, utilisez le code de l'application.",
            )
            return redirect(redirect_to)
        else:
            messages.error(
                request,
                "Code incorrect. Attendez le prochain code (30 s), vérifiez l'heure du téléphone et réessayez.",
            )
        return redirect(redirect_to)

    if action == 'totp_annuler':
        if user.mfa_methode != User.MFA_TOTP:
            User.objects.filter(pk=user.pk).update(totp_secret='')
        request.session.pop('totp_pending_secret', None)
        messages.info(request, "Configuration Authenticator annulée.")
        return redirect(redirect_to)

    return None
