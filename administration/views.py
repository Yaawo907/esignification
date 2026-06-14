from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.html import escape
from django.contrib import messages
from accounts.models import User
from .models import ConfigurationPlateforme, TexteLegal, ModeleEmail, LotMerkle, PisteAudit
from securite.audit import journaliser


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
        'huissiers_attente': ProfilHuissier.objects.filter(statut='en_attente').count(),
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
        email = escape(request.POST.get('email', '').strip().lower())
        if not email:
            messages.error(request, "L'adresse email est obligatoire.")
            return redirect(request.path)
        if User.objects.filter(email=email).exists():
            messages.error(request, "Un compte existe déjà avec cet email.")
            return redirect(request.path)
        # Créer un token d'activation
        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        from notifications.service import envoyer_activation_huissier
        token_brut, _ = creer_token_activation(email, TokenActivation.ACTIVATION_HUISSIER)
        envoyer_activation_huissier(email, token_brut)
        journaliser(request.user, 'invitation_huissier_envoyee', description=f"Email: {email}", request=request)
        messages.success(request, f"Lien d'activation envoyé à {email}.")
        return redirect('administration:liste_huissiers')
    return render(request, 'administration/creer_huissier.html')


@login_required
@admin_required
def liste_huissiers(request):
    from huissiers.models import ProfilHuissier
    statut = request.GET.get('statut', '')
    qs = ProfilHuissier.objects.select_related('user').order_by('-date_creation')
    total_all = qs.count()
    total_actif = qs.filter(statut='actif').count()
    total_inactif = qs.filter(statut='inactif').count()
    total_attente = qs.filter(statut='en_attente').count()
    if statut:
        qs = qs.filter(statut=statut)
    return render(request, 'administration/liste_huissiers.html', {
        'huissiers': qs,
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
    huissier = get_object_or_404(ProfilHuissier, uuid=uuid, statut='en_attente')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    try:
        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        from notifications.service import envoyer_activation_huissier
        token_brut, _ = creer_token_activation(huissier.user.email, TokenActivation.ACTIVATION_HUISSIER)
        envoyer_activation_huissier(huissier.user.email, token_brut)
        journaliser(request.user, 'invitation_huissier_renvoyee', 'ProfilHuissier', huissier.uuid,
                    description=f"Renvoi à {huissier.user.email}", request=request)
        if is_ajax:
            return JsonResponse({'success': True, 'message': f"Invitation renvoyée à {huissier.user.email}."})
        messages.success(request, f"Invitation renvoyée à {huissier.user.email}.")
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, "Erreur lors du renvoi de l'invitation.")
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
def audit(request):
    qs = PisteAudit.objects.order_by('-date')[:500]
    return render(request, 'administration/audit.html', {'activites': qs})
