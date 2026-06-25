import pyotp
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.crypto import get_random_string
from .models import User, TokenActivation
from .forms import (ConnexionForm, MFACodeForm, InscriptionHuissierForm,
                    InscriptionJusticiableForm, ModificationMotDePasseForm,
                    RecuperationCompteForm, NouveauMotDePasseForm)
from securite.tokens import creer_token_activation, valider_token, marquer_token_utilise
from securite.audit import journaliser
from notifications.service import envoyer_recuperation_mdp


@require_http_methods(["GET", "POST"])
def connexion(request):
    if request.user.is_authenticated:
        return redirect(redirect_apres_connexion(request.user))
    form = ConnexionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.cleaned_data['user']
        # Stocker user en session pour MFA
        request.session['pre_auth_user_id'] = user.pk
        request.session['pre_auth_next'] = request.GET.get('next', '')
        # Envoyer code MFA si méthode email ou OTP
        if user.mfa_active and not user.is_superuser and user.mfa_methode in [User.MFA_EMAIL, User.MFA_OTP]:
            _envoyer_code_mfa(user)
        journaliser(user, 'connexion_tentative', request=request)
        return redirect('accounts:mfa_verification')
    return render(request, 'accounts/connexion.html', {'form': form})


def _envoyer_code_mfa(user):
    from notifications.service import envoyer_email
    code = get_random_string(6, '0123456789')
    user.mfa_code = code
    user.mfa_code_expiry = timezone.now() + timedelta(minutes=10)
    user.save(update_fields=['mfa_code', 'mfa_code_expiry'])
    corps = f"""
    <div style="font-family:Arial,sans-serif;padding:24px;">
      <h2 style="color:#1a3c6e;">Code de vérification</h2>
      <p>Votre code de connexion est :</p>
      <p style="font-size:32px;font-weight:bold;letter-spacing:8px;color:#1a3c6e;">{code}</p>
      <p style="color:#888;">Ce code expire dans 10 minutes.</p>
    </div>"""
    envoyer_email(user.email, "Code de vérification — e-Signification Bénin", corps)


@require_http_methods(["GET", "POST"])
def mfa_verification(request):
    user_id = request.session.get('pre_auth_user_id')
    if not user_id:
        return redirect('accounts:connexion')
    user = get_object_or_404(User, pk=user_id)
    # Bypass MFA pour les superusers
    if user.is_superuser or not user.mfa_active:
        user.is_active = True
        user.derniere_connexion = timezone.now()
        user.save(update_fields=['derniere_connexion', 'is_active'])
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        del request.session['pre_auth_user_id']
        journaliser(user, 'connexion_reussie', request=request)
        next_url = request.session.pop('pre_auth_next', '')
        return redirect(next_url or redirect_apres_connexion(user))
    form = MFACodeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['code']
        valide = False
        if user.mfa_methode == User.MFA_TOTP:
            totp = pyotp.TOTP(user.totp_secret)
            valide = totp.verify(code)
        else:
            if (user.mfa_code == code and
                    user.mfa_code_expiry and
                    timezone.now() < user.mfa_code_expiry):
                valide = True
                user.mfa_code = ''
                user.mfa_code_expiry = None
                user.save(update_fields=['mfa_code', 'mfa_code_expiry'])
        if valide:
            user.is_active = True
            user.derniere_connexion = timezone.now()
            user.save(update_fields=['derniere_connexion'])
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            del request.session['pre_auth_user_id']
            journaliser(user, 'connexion_reussie', request=request)
            next_url = request.session.pop('pre_auth_next', '')
            return redirect(next_url or redirect_apres_connexion(user))
        else:
            messages.error(request, "Code incorrect ou expiré.")
    return render(request, 'accounts/mfa_verification.html', {'form': form, 'methode': user.mfa_methode})


def redirect_apres_connexion(user):
    if user.role == User.ADMIN:
        return '/administration/'
    elif user.role in [User.HUISSIER, User.CLERC]:
        return '/huissier/'
    elif user.role == User.JUSTICIABLE:
        return '/justiciable/'
    return '/'


@login_required
def deconnexion(request):
    journaliser(request.user, 'deconnexion', request=request)
    logout(request)
    messages.success(request, "Vous avez été déconnecté.")
    return redirect('accounts:connexion')


@require_http_methods(["GET", "POST"])
def inscription_huissier(request):
    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.ACTIVATION_HUISSIER)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})
    form = InscriptionHuissierForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(
            email=token_obj.email,
            password=d['mot_de_passe'],
            role=User.HUISSIER,
            is_active=True,
        )
        from huissiers.models import ProfilHuissier
        ProfilHuissier.objects.create(
            user=user,
            nom=d['nom'],
            prenom=d['prenom'],
            nom_etude=d['nom_etude'],
            ifu=d['ifu'],
            npi=d['npi'],
            adresse=d['adresse'],
            telephone=d['telephone'],
            statut='actif',
        )
        marquer_token_utilise(token_obj)
        journaliser(user, 'inscription_huissier_complete', request=request)
        # Connecter directement l'huissier après activation
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, "Compte activé avec succès. Bienvenue !")
        return redirect('/huissier/')
    return render(request, 'accounts/inscription_huissier.html', {'form': form, 'email': token_obj.email})


@require_http_methods(["GET", "POST"])
def inscription_justiciable(request):
    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.INVITATION_JUSTICIABLE)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})
    form = InscriptionJusticiableForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user = User.objects.create_user(
            email=d['email_domicile'],
            password=d['mot_de_passe'],
            role=User.JUSTICIABLE,
            is_active=False,
        )
        from justiciables.models import ProfilJusticiable
        profil = ProfilJusticiable.objects.create(
            user=user,
            type_compte=d['type_compte'],
            nom=d['nom'],
            prenom=d.get('prenom', ''),
            ifu=d.get('ifu', ''),
            npi=d.get('npi', ''),
            adresse=d['adresse'],
            telephone=d['telephone'],
            email_domicile=d['email_domicile'],
        )
        # Envoyer confirmation email domicile
        _envoyer_confirmation_domicile(user, d['email_domicile'])
        marquer_token_utilise(token_obj)
        journaliser(user, 'inscription_justiciable_en_attente', request=request)
        return render(request, 'accounts/confirmation_envoyee.html', {'email': d['email_domicile']})
    return render(request, 'accounts/inscription_justiciable.html', {'form': form})


def _envoyer_confirmation_domicile(user, email_domicile):
    from django.conf import settings
    token_brut, _ = creer_token_activation(email_domicile, TokenActivation.CONFIRMATION_EMAIL, {'user_id': user.pk}, heures=48)
    lien = f"{settings.SITE_URL}/confirmer-domicile/?token={token_brut}"
    from notifications.service import envoyer_email
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:8px;">
      <div style="background:#1a3c6e;padding:20px 24px;border-radius:6px 6px 0 0;margin:-24px -24px 24px -24px;">
        <h1 style="color:#fff;margin:0;font-size:20px;font-weight:600;">e-Signification Bénin</h1>
      </div>
      <h2 style="color:#1a3c6e;font-size:18px;">Confirmez votre domicile électronique</h2>
      <p style="color:#374151;">Cliquez sur le bouton ci-dessous pour confirmer votre adresse email d'élection de domicile :</p>

      <table width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0;">
        <tr>
          <td align="center">
            <table cellpadding="0" cellspacing="0">
              <tr>
                <td style="background:#1a3c6e;border-radius:8px;padding:14px 32px;">
                  <a href="{lien}" style="color:#ffffff;text-decoration:none;font-size:16px;font-weight:600;display:inline-block;">
                    ✉ Confirmer mon adresse
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>

      <p style="color:#6b7280;font-size:13px;">Si le bouton ne fonctionne pas, copiez ce lien :</p>
      <p style="word-break:break-all;font-size:12px;">
        <a href="{lien}" style="color:#1a3c6e;">{lien}</a>
      </p>
      <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
      <p style="color:#9ca3af;font-size:12px;margin:0;">Ce lien est valable 48 heures.</p>
    </div>"""
    corps_texte = f"""Confirmez votre domicile électronique

Cliquez sur le lien suivant pour confirmer votre adresse :

{lien}

Ce lien est valable 48 heures.
"""
    envoyer_email(email_domicile, "Confirmez votre domicile électronique", corps, corps_texte)


def confirmer_domicile(request):
    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.CONFIRMATION_EMAIL)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})
    user_id = token_obj.metadata.get('user_id')
    try:
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save(update_fields=['is_active'])
        profil = user.profil_justiciable
        profil.email_domicile_verifie = True
        profil.save(update_fields=['email_domicile_verifie'])
        marquer_token_utilise(token_obj)
        journaliser(user, 'domicile_electronique_confirme', request=request)
        messages.success(request, "Votre domicile électronique a été confirmé. Vous pouvez vous connecter.")
        return redirect('accounts:connexion')
    except User.DoesNotExist:
        return render(request, 'accounts/token_invalide.html', {'erreur': 'Utilisateur introuvable.'})


@login_required
def modifier_mot_de_passe(request):
    form = ModificationMotDePasseForm(user=request.user, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        request.user.set_password(form.cleaned_data['nouveau_mdp'])
        request.user.save()
        journaliser(request.user, 'modification_mot_de_passe', request=request)
        messages.success(request, "Mot de passe modifié avec succès.")
        return redirect('accounts:connexion')
    return render(request, 'accounts/modifier_mdp.html', {'form': form})


def recuperation_compte(request):
    form = RecuperationCompteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].lower()
        try:
            user = User.objects.get(email=email, is_active=True)
            token_brut, _ = creer_token_activation(email, TokenActivation.RECUPERATION_MDP, heures=2)
            envoyer_recuperation_mdp(email, token_brut)
        except User.DoesNotExist:
            pass  # Silencieux pour ne pas révéler l'existence du compte
        return render(request, 'accounts/recuperation_envoyee.html')
    return render(request, 'accounts/recuperation_compte.html', {'form': form})


def reinitialiser_mdp(request):
    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.RECUPERATION_MDP)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})
    form = NouveauMotDePasseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = User.objects.get(email=token_obj.email)
            user.set_password(form.cleaned_data['nouveau_mdp'])
            user.save()
            marquer_token_utilise(token_obj)
            journaliser(user, 'reinitialisation_mot_de_passe', request=request)
            messages.success(request, "Mot de passe réinitialisé. Vous pouvez vous connecter.")
            return redirect('accounts:connexion')
        except User.DoesNotExist:
            return render(request, 'accounts/token_invalide.html', {'erreur': 'Compte introuvable.'})
    return render(request, 'accounts/reinitialiser_mdp.html', {'form': form})


def inscription_clerc(request):
    """Activation du compte clerc via le lien d'invitation envoyé par l'huissier."""
    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.ACTIVATION_CLERC)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})

    # Lire les métadonnées stockées dans le token
    meta = token_obj.metadata or {}
    email = token_obj.email
    prenom = meta.get('prenom', '')
    nom = meta.get('nom', '')

    if request.method == 'POST':
        nouveau_mdp = request.POST.get('nouveau_mdp', '').strip()
        confirmer_mdp = request.POST.get('confirmer_mdp', '').strip()
        erreur_form = None

        if len(nouveau_mdp) < 10:
            erreur_form = "Le mot de passe doit contenir au moins 10 caractères."
        elif nouveau_mdp != confirmer_mdp:
            erreur_form = "Les mots de passe ne correspondent pas."

        if erreur_form:
            return render(request, 'accounts/inscription_clerc.html', {
                'email': email, 'prenom': prenom, 'nom': nom,
                'erreur': erreur_form,
            })

        try:
            # Créer ou récupérer le compte utilisateur
            user, created = User.objects.get_or_create(
                email=email,
                defaults={'role': User.CLERC, 'is_active': False}
            )
            if not created and user.role != User.CLERC:
                return render(request, 'accounts/token_invalide.html',
                              {'erreur': 'Un compte avec cet email existe déjà avec un rôle différent.'})

            user.set_password(nouveau_mdp)
            user.is_active = True
            user.role = User.CLERC
            user.save()

            # Créer le ProfilClerc si inexistant
            from huissiers.models import ProfilHuissier, ProfilClerc
            huissier_uuid = meta.get('huissier_uuid')
            huissier = get_object_or_404(ProfilHuissier, uuid=huissier_uuid)
            ProfilClerc.objects.get_or_create(
                user=user,
                defaults={
                    'huissier': huissier,
                    'nom': nom,
                    'prenom': prenom,
                    'telephone': meta.get('telephone', ''),
                    'actif': True,
                }
            )

            marquer_token_utilise(token_obj)
            journaliser(user, 'inscription_clerc', request=request)
            messages.success(request, "Votre compte clerc a été activé. Vous pouvez vous connecter.")
            return redirect('accounts:connexion')

        except Exception as exc:
            return render(request, 'accounts/token_invalide.html',
                          {'erreur': f"Erreur lors de l'activation : {exc}"})

    return render(request, 'accounts/inscription_clerc.html', {
        'email': email, 'prenom': prenom, 'nom': nom,
    })
