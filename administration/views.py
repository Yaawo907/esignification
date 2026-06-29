import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.html import escape
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils import timezone as tz
from accounts.models import User
from .models import ConfigurationPlateforme, TexteLegal, ModeleEmail, LotMerkle, PisteAudit
from securite.audit import journaliser

logger = logging.getLogger(__name__)


def _lien_inscription_huissier(request, token_brut: str) -> str:
    """Lien d'activation — SITE_URL en priorité (fiable pour les emails)."""
    from django.conf import settings
    path = reverse('accounts:inscription_huissier') + f'?token={token_brut}'
    base = settings.SITE_URL.rstrip('/')
    if base:
        return f"{base}{path}"
    if request:
        try:
            return request.build_absolute_uri(path)
        except Exception:
            pass
    return f"http://localhost:8000{path}"


def _message_erreur_email(exc: Exception) -> str:
    from django.conf import settings
    if isinstance(exc, ModuleNotFoundError) and 'apps' in str(exc):
        return (
            "Configuration email incorrecte : EMAIL_BACKEND pointe vers un module "
            "'apps.*' (probablement un autre projet Django). "
            "Vérifiez votre fichier .env ou les variables d'environnement Windows."
        )
    msg = "Impossible d'envoyer l'email. Vérifiez la configuration SMTP."
    if settings.DEBUG:
        msg = f"{msg} Détail : {type(exc).__name__}: {exc}"
    return msg


def _invitations_huissier_queryset():
    from accounts.models import TokenActivation
    emails_inscrits = User.objects.filter(role=User.HUISSIER).values_list('email', flat=True)
    return TokenActivation.objects.filter(
        type_token=TokenActivation.ACTIVATION_HUISSIER,
        utilise=False,
        date_expiration__gt=tz.now(),
    ).exclude(email__in=emails_inscrits).order_by('-date_creation')


def _token_invitation_huissier_actif(email: str):
    from accounts.models import TokenActivation
    return TokenActivation.objects.filter(
        email=email,
        type_token=TokenActivation.ACTIVATION_HUISSIER,
        utilise=False,
        date_expiration__gt=tz.now(),
    ).first()


def _envoyer_invitation_huissier(request, email: str, token_brut: str):
    from notifications.service import envoyer_activation_huissier
    lien = _lien_inscription_huissier(request, token_brut)
    envoyer_activation_huissier(email, token_brut, lien=lien, sync=True)


def admin_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.ADMIN:
            return redirect(f'/connexion/?next={request.path}')
        return view_func(request, *args, **kwargs)
    return wrapped


@login_required
@admin_required
def tableau_de_bord(request):
    from huissiers.models import ProfilHuissier
    from justiciables.models import ProfilJusticiable
    from significations.models import Signification
    stats = {
        'huissiers_actifs': ProfilHuissier.objects.filter(statut='actif').count(),
        'huissiers_inactifs': ProfilHuissier.objects.filter(statut='inactif').count(),
        'huissiers_attente': (
            ProfilHuissier.objects.filter(statut='en_attente').count()
            + _invitations_huissier_queryset().count()
        ),
        'justiciables': ProfilJusticiable.objects.filter(email_domicile_verifie=True).count(),
        'significations_total': Signification.objects.count(),
        'significations_attente': Signification.objects.filter(statut__in=['en_attente', 'relance_1', 'relance_2']).count(),
    }
    huissiers_recents = ProfilHuissier.objects.order_by('-date_creation')[:5]
    significations_recentes = Signification.objects.order_by('-date_envoi')[:5]
    activites = PisteAudit.objects.order_by('-date')[:10]
    return render(request, 'administration/tableau_de_bord.html', {
        'stats': stats, 'huissiers_recents': huissiers_recents,
        'significations_recentes': significations_recentes, 'activites': activites,
    })


@login_required
@admin_required
@require_http_methods(["GET", "POST"])
def creer_huissier(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if not email:
            messages.error(request, "L'adresse email est obligatoire.")
            return redirect(request.path)
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Adresse email invalide.")
            return redirect(request.path)
        if User.objects.filter(email=email).exists():
            messages.error(request, "Un compte existe déjà avec cet email.")
            return redirect(request.path)
        if _token_invitation_huissier_actif(email):
            messages.warning(
                request,
                f"Une invitation active existe déjà pour {email}. "
                f"Utilisez « Renvoyer » depuis la liste ou attendez l'expiration du lien."
            )
            return redirect('administration:liste_huissiers')

        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        token_brut, token_hache = creer_token_activation(email, TokenActivation.ACTIVATION_HUISSIER)
        try:
            _envoyer_invitation_huissier(request, email, token_brut)
        except Exception as exc:
            logger.exception("Echec envoi invitation huissier à %s", email)
            TokenActivation.objects.filter(token=token_hache).delete()
            messages.error(request, _message_erreur_email(exc))
            return redirect(request.path)

        journaliser(request.user, 'invitation_huissier_envoyee', description=f"Email: {email}", request=request)
        messages.success(request, f"Lien d'activation envoyé à {email}.")
        return redirect('administration:liste_huissiers')
    return render(request, 'administration/creer_huissier.html')


@login_required
@admin_required
def liste_huissiers(request):
    from huissiers.models import ProfilHuissier
    statut = request.GET.get('statut', '')
    invitations = _invitations_huissier_queryset()
    nb_invitations = invitations.count()
    qs = ProfilHuissier.objects.select_related('user').order_by('-date_creation')
    total_actif = qs.filter(statut='actif').count()
    total_inactif = qs.filter(statut='inactif').count()
    total_profils_attente = qs.filter(statut='en_attente').count()
    total_attente = nb_invitations + total_profils_attente
    total_all = qs.count() + nb_invitations

    if statut == 'en_attente':
        qs = qs.filter(statut='en_attente')
    elif statut:
        qs = qs.filter(statut=statut)
        invitations = invitations.none()

    return render(request, 'administration/liste_huissiers.html', {
        'huissiers': qs,
        'invitations': invitations,
        'statut_filtre': statut,
        'total_all': total_all,
        'total_actif': total_actif,
        'total_inactif': total_inactif,
        'total_attente': total_attente,
    })


@login_required
@admin_required
@require_http_methods(["POST"])
def changer_statut_huissier(request, uuid):
    from huissiers.models import ProfilHuissier
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    huissier = get_object_or_404(ProfilHuissier, uuid=uuid)
    nouveau_statut = escape(request.POST.get('statut', ''))
    if nouveau_statut not in ['actif', 'inactif']:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Statut invalide.'}, status=400)
        messages.error(request, "Statut invalide.")
        return redirect('administration:liste_huissiers')
    ancien = huissier.statut
    huissier.statut = nouveau_statut
    huissier.save(update_fields=['statut'])
    huissier.user.is_active = (nouveau_statut == 'actif')
    huissier.user.save(update_fields=['is_active'])
    journaliser(request.user, f'statut_huissier_{nouveau_statut}', 'ProfilHuissier', huissier.uuid,
                description=f"{huissier} : {ancien} → {nouveau_statut}", request=request)
    label = 'Actif' if nouveau_statut == 'actif' else 'Inactif'
    if is_ajax:
        return JsonResponse({
            'success': True,
            'nouveau_statut': nouveau_statut,
            'label': label,
            'nom': f"Me {huissier.prenom} {huissier.nom}",
        })
    messages.success(request, f"Statut de {huissier} changé en {nouveau_statut}.")
    return redirect('administration:liste_huissiers')


@login_required
@admin_required
@require_http_methods(["POST"])
def renvoyer_invitation_huissier(request, uuid):
    from huissiers.models import ProfilHuissier
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        huissier = ProfilHuissier.objects.get(uuid=uuid, statut='en_attente')
    except ProfilHuissier.DoesNotExist:
        msg = "Huissier introuvable ou déjà activé. Actualisez la page."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=404)
        messages.error(request, msg)
        return redirect('administration:liste_huissiers')

    from securite.tokens import creer_token_activation
    from accounts.models import TokenActivation
    email = huissier.user.email
    token_brut, token_hache = creer_token_activation(email, TokenActivation.ACTIVATION_HUISSIER)
    try:
        _envoyer_invitation_huissier(request, email, token_brut)
    except Exception as exc:
        logger.exception("Echec renvoi invitation huissier (profil) à %s", email)
        TokenActivation.objects.filter(token=token_hache).delete()
        err = _message_erreur_email(exc)
        if is_ajax:
            return JsonResponse({'success': False, 'error': err}, status=500)
        messages.error(request, err)
        return redirect('administration:liste_huissiers')

    TokenActivation.objects.filter(
        email=email,
        type_token=TokenActivation.ACTIVATION_HUISSIER,
        utilise=False,
    ).exclude(token=token_hache).update(utilise=True)
    journaliser(request.user, 'invitation_huissier_renvoyee', 'ProfilHuissier', huissier.uuid,
                description=f"Renvoi à {email}", request=request)
    if is_ajax:
        return JsonResponse({'success': True, 'message': f"Invitation renvoyée à {email}.", 'reload': True})
    messages.success(request, f"Invitation renvoyée à {email}.")
    return redirect('administration:liste_huissiers')


@login_required
@admin_required
@require_http_methods(["POST"])
def renvoyer_invitation_token_huissier(request, uuid):
    from accounts.models import TokenActivation
    from securite.tokens import creer_token_activation
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        token_obj = TokenActivation.objects.get(
            uuid=uuid,
            type_token=TokenActivation.ACTIVATION_HUISSIER,
            utilise=False,
            date_expiration__gt=tz.now(),
        )
    except TokenActivation.DoesNotExist:
        msg = "Invitation introuvable ou expirée. Actualisez la page."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=404)
        messages.error(request, msg)
        return redirect('administration:liste_huissiers')

    email = token_obj.email
    if User.objects.filter(email=email).exists():
        msg = "Un compte existe déjà avec cet email."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('administration:liste_huissiers')

    token_brut, token_hache = creer_token_activation(email, TokenActivation.ACTIVATION_HUISSIER)
    try:
        _envoyer_invitation_huissier(request, email, token_brut)
    except Exception as exc:
        logger.exception("Echec renvoi invitation huissier (profil) à %s", email)
        TokenActivation.objects.filter(token=token_hache).delete()
        err = _message_erreur_email(exc)
        if is_ajax:
            return JsonResponse({'success': False, 'error': err}, status=500)
        messages.error(request, err)
        return redirect('administration:liste_huissiers')

    TokenActivation.objects.filter(
        email=email,
        type_token=TokenActivation.ACTIVATION_HUISSIER,
        utilise=False,
    ).exclude(token=token_hache).update(utilise=True)
    journaliser(
        request.user, 'invitation_huissier_renvoyee', 'TokenActivation', token_obj.uuid,
        description=f"Renvoi à {email}", request=request,
    )
    if is_ajax:
        return JsonResponse({'success': True, 'message': f"Invitation renvoyée à {email}.", 'reload': True})
    messages.success(request, f"Invitation renvoyée à {email}.")
    return redirect('administration:liste_huissiers')


@login_required
@admin_required
@require_http_methods(["POST"])
def supprimer_invitation_huissier(request, uuid):
    from accounts.models import TokenActivation
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        token_obj = TokenActivation.objects.get(
            uuid=uuid,
            type_token=TokenActivation.ACTIVATION_HUISSIER,
            utilise=False,
        )
    except TokenActivation.DoesNotExist:
        msg = "Invitation introuvable ou déjà supprimée."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=404)
        messages.error(request, msg)
        return redirect('administration:liste_huissiers')

    email = token_obj.email
    if User.objects.filter(email=email, role=User.HUISSIER).exists():
        msg = "Un compte huissier existe déjà pour cet email."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('administration:liste_huissiers')

    TokenActivation.objects.filter(
        email=email,
        type_token=TokenActivation.ACTIVATION_HUISSIER,
        utilise=False,
    ).update(utilise=True)
    journaliser(
        request.user, 'invitation_huissier_supprimee', 'TokenActivation', token_obj.uuid,
        description=f"Invitation annulée pour {email}", request=request,
    )
    if is_ajax:
        return JsonResponse({
            'success': True,
            'message': f"Invitation supprimée pour {email}.",
            'row_id': f"inv-{token_obj.uuid}",
        })
    messages.success(request, f"Invitation supprimée pour {email}.")
    return redirect('administration:liste_huissiers')


@login_required
@admin_required
def configuration(request):
    config = ConfigurationPlateforme.get()
    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'general':
            config.nom_plateforme = escape(request.POST.get('nom_plateforme', config.nom_plateforme))
            config.pays = escape(request.POST.get('pays', config.pays))
            config.langue_defaut = request.POST.get('langue_defaut', config.langue_defaut)
            config.article_loi_signification = escape(request.POST.get('article_loi', ''))
            config.decret_reference = escape(request.POST.get('decret_reference', ''))
            config.nom_autorite_tutelle = escape(request.POST.get('nom_autorite', ''))
            config.email_contact = escape(request.POST.get('email_contact', ''))
            config.copyright_texte = escape(request.POST.get('copyright_texte', config.copyright_texte))
            config.methode_2fa_defaut = request.POST.get('methode_2fa', config.methode_2fa_defaut)
            config.delai_relance_1_jours = int(request.POST.get('delai_relance_1', 3))
            config.delai_relance_2_jours = int(request.POST.get('delai_relance_2', 6))
            config.save()
            journaliser(request.user, 'configuration_generale_modifiee', request=request)
            messages.success(request, "Configuration enregistrée.")
        elif action == 'certigna':
            config.certigna_active = request.POST.get('certigna_active') == 'on'
            config.certigna_tsa_url = escape(request.POST.get('certigna_url', ''))
            config.certigna_login = escape(request.POST.get('certigna_login', ''))
            pwd = request.POST.get('certigna_password', '')
            if pwd:
                from securite.chiffrement import chiffrer_texte
                config.certigna_password_chiffre = chiffrer_texte(pwd)
            config.certigna_oid = escape(request.POST.get('certigna_oid', ''))
            import datetime
            heure_str = request.POST.get('certigna_heure', '00:00')
            try:
                h, m = heure_str.split(':')
                config.certigna_heure_lot = datetime.time(int(h), int(m))
            except Exception:
                pass
            config.certigna_seuil_alerte_jetons = int(request.POST.get('seuil_jetons', 20))
            config.save()
            journaliser(request.user, 'configuration_certigna_modifiee', request=request)
            messages.success(request, "Configuration Certigna enregistrée.")
        elif action == 'yousign':
            config.yousign_active = request.POST.get('yousign_active') == 'on'
            config.yousign_mode = request.POST.get('yousign_mode', 'sandbox')
            api_key = request.POST.get('yousign_api_key', '').strip()
            if api_key:
                from securite.chiffrement import chiffrer_texte
                config.yousign_api_key_chiffre = chiffrer_texte(api_key)
            webhook_secret = request.POST.get('yousign_webhook_secret', '').strip()
            if webhook_secret:
                from securite.chiffrement import chiffrer_texte
                config.yousign_webhook_secret_chiffre = chiffrer_texte(webhook_secret)
            config.save()
            journaliser(request.user, 'configuration_yousign_modifiee', request=request)
            messages.success(request, "Configuration Yousign enregistrée.")
        elif action == 'logos':
            import imghdr
            for champ, nom in [('logo_pays', 'logo_pays'), ('logo_chambre', 'logo_chambre')]:
                fichier = request.FILES.get(nom)
                if fichier:
                    # Vérification : uniquement PNG ou JPEG, max 2 Mo
                    if fichier.size > 2 * 1024 * 1024:
                        messages.error(request, f"Le fichier {nom} dépasse 2 Mo.")
                        return redirect('administration:configuration')
                    entete = b''.join(chunk for chunk in fichier.chunks(chunk_size=32))[:32]
                    type_img = imghdr.what(None, h=entete)
                    if type_img not in ('png', 'jpeg'):
                        messages.error(request, f"Format non supporté pour {nom} (PNG ou JPEG uniquement).")
                        return redirect('administration:configuration')
                    fichier.seek(0)
                    ancien = getattr(config, champ)
                    if ancien:
                        try:
                            ancien.delete(save=False)
                        except Exception:
                            pass
                    setattr(config, champ, fichier)
            config.save()
            journaliser(request.user, 'logos_certificat_modifies', request=request)
            messages.success(request, "Logos mis à jour avec succès.")
        return redirect('administration:configuration')
    return render(request, 'administration/configuration.html', {'config': config})


_TITRES_TEXTE_LEGAL_DEFAUT = {
    TexteLegal.TYPE_CGU: "Conditions Générales d'Utilisation",
    TexteLegal.TYPE_CONFIDENTIALITE: 'Politique de confidentialité',
    TexteLegal.TYPE_MENTIONS: 'Mentions légales',
}


def _langue_courante(request):
    from django.utils import translation
    langue = translation.get_language() or 'fr'
    return langue.split('-')[0].lower()


def texte_legal_public(request, type_texte):
    """Page publique CGU, confidentialité, mentions légales."""
    if type_texte not in _TITRES_TEXTE_LEGAL_DEFAUT:
        raise Http404
    langue = _langue_courante(request)
    texte = (
        TexteLegal.objects.filter(type_texte=type_texte, langue=langue, actif=True).first()
        or TexteLegal.objects.filter(type_texte=type_texte, actif=True).order_by('langue').first()
    )
    titre_page = texte.titre if texte else _TITRES_TEXTE_LEGAL_DEFAUT[type_texte]
    return render(request, 'pages/texte_legal.html', {
        'texte': texte,
        'titre_page': titre_page,
        'type_texte': type_texte,
    })


@login_required
@admin_required
def gerer_textes_legaux(request):
    textes = TexteLegal.objects.all().order_by('type_texte', 'langue')
    if request.method == 'POST':
        uuid_texte = request.POST.get('uuid', '')
        type_t = request.POST.get('type_texte', '')
        langue = request.POST.get('langue', 'fr')
        titre = escape(request.POST.get('titre', ''))
        contenu = request.POST.get('contenu_html', '')
        version = escape(request.POST.get('version', '1.0'))
        if uuid_texte:
            texte = get_object_or_404(TexteLegal, uuid=uuid_texte)
        else:
            texte, _ = TexteLegal.objects.get_or_create(type_texte=type_t, langue=langue, defaults={'titre': titre, 'contenu_html': ''})
        texte.titre = titre
        texte.contenu_html = contenu
        texte.version = version
        texte.save()
        journaliser(request.user, 'texte_legal_modifie', 'TexteLegal', texte.uuid, request=request)
        messages.success(request, "Texte légal enregistré.")
        return redirect('administration:textes_legaux')
    return render(request, 'administration/textes_legaux.html', {'textes': textes})


@login_required
@admin_required
def profil(request):
    """Sécurité du compte administrateur — 2FA et mot de passe."""
    from accounts.forms import ModificationMotDePasseForm
    from accounts.mfa_profil import contexte_mfa_profil, traiter_action_mfa_profil

    user = request.user
    form_mdp = ModificationMotDePasseForm(user=user)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'changer_mdp':
            form_mdp = ModificationMotDePasseForm(user=user, data=request.POST)
            if form_mdp.is_valid():
                user.set_password(form_mdp.cleaned_data['nouveau_mdp'])
                user.save()
                journaliser(user, 'modification_mot_de_passe', request=request)
                messages.success(request, "Mot de passe modifié. Reconnectez-vous.")
                from django.contrib.auth import logout
                logout(request)
                return redirect('/connexion/')
        else:
            mfa_redirect = traiter_action_mfa_profil(
                request, user, 'administration:profil', telephone='',
            )
            if mfa_redirect:
                return mfa_redirect

    user.refresh_from_db(fields=['mfa_methode', 'totp_secret'])

    return render(request, 'administration/profil.html', {
        'form_mdp': form_mdp,
        **contexte_mfa_profil(user, request.session),
    })


@login_required
@admin_required
def audit(request):
    qs = PisteAudit.objects.order_by('-date')[:500]
    return render(request, 'administration/audit.html', {'activites': qs})


@login_required
@admin_required
@require_http_methods(["POST"])
def tester_yousign(request):
    """Teste la connexion Yousign — lit la cle depuis le body JSON."""
    import json as _json
    import urllib.request as _req
    import urllib.error as _uerr
    from django.http import JsonResponse

    api_key = ''
    mode = 'sandbox'
    try:
        body = _json.loads(request.body or '{}')
        api_key = body.get('api_key', '').strip()
        mode = body.get('mode', 'sandbox')
    except Exception:
        pass

    if not api_key:
        config = ConfigurationPlateforme.get()
        if not config.yousign_api_key_chiffre:
            return JsonResponse({'success': False,
                                 'message': 'Aucune cle API. Saisissez-la puis cliquez Tester.'})
        try:
            from securite.chiffrement import dechiffrer_texte
            api_key = dechiffrer_texte(config.yousign_api_key_chiffre)
            mode = config.yousign_mode
        except Exception:
            return JsonResponse({'success': False, 'message': 'Erreur dechiffrement cle.'})

    base = ('https://api-sandbox.yousign.app/v3' if mode == 'sandbox'
            else 'https://api.yousign.app/v3')
    url = base + '/signature_requests?items_per_page=1'
    try:
        r = _req.Request(url, headers={
            'Authorization': 'Bearer ' + api_key,
            'Accept': 'application/json',
        })
        with _req.urlopen(r, timeout=10) as resp:
            resp.read()
        return JsonResponse({'success': True,
                             'message': 'Connexion Yousign OK — mode ' + mode + '.'})
    except _uerr.HTTPError as e:
        if e.code == 401:
            return JsonResponse({'success': False, 'message': 'Cle API invalide (401).'})
        if e.code == 403:
            return JsonResponse({'success': False, 'message': 'Acces refuse (403).'})
        return JsonResponse({'success': False, 'message': 'Erreur HTTP ' + str(e.code) + '.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'Erreur reseau : ' + str(e)})
