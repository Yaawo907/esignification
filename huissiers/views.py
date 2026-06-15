from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.html import escape
from accounts.models import User
from .models import ProfilHuissier
from significations.models import Signification


def huissier_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role not in [User.HUISSIER, User.CLERC]:
            return redirect(f'/connexion/?next={request.path}')
        return view_func(request, *args, **kwargs)
    return wrapped


@login_required
@huissier_required
def tableau_de_bord(request):
    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    significations = Signification.objects.filter(huissier=huissier).select_related('justiciable', 'certificat')
    stats = {
        'envoyees': significations.count(),
        'en_attente': significations.filter(statut__in=['en_attente', 'relance_1', 'relance_2']).count(),
        'acceptees': significations.filter(statut__in=['acceptee', 'repondu']).count(),
        'reponses_non_vues': significations.filter(statut='repondu', reponse__vue_par_huissier=False).count(),
    }
    recentes = significations.order_by('-date_envoi')[:10]
    from justiciables.models import DemandeModificationProfil
    nb_demandes_modif = DemandeModificationProfil.objects.filter(
        huissier=huissier, statut='en_attente'
    ).count()
    from messagerie.models import Message
    from django.db.models import Q
    nb_messages_non_lus = Message.objects.filter(
        Q(conversation__participant_1=request.user) | Q(conversation__participant_2=request.user),
        lu=False
    ).exclude(auteur=request.user).count()
    return render(request, 'huissiers/tableau_de_bord.html', {
        'huissier': huissier,
        'stats': stats,
        'significations_recentes': recentes,
        'nb_demandes_modif': nb_demandes_modif,
        'nb_messages_non_lus': nb_messages_non_lus,
    })


@login_required
@huissier_required
def rechercher_justiciable(request):
    resultats = []
    q = escape(request.GET.get('q', '').strip())
    filtre = request.GET.get('filtre', 'tous')
    if q and len(q) >= 2:
        from justiciables.models import ProfilJusticiable
        from django.db.models import Q
        qs = ProfilJusticiable.objects.filter(email_domicile_verifie=True)
        if filtre == 'ifu':
            qs = qs.filter(ifu__icontains=q)
        elif filtre == 'npi':
            qs = qs.filter(npi__icontains=q)
        elif filtre == 'email':
            qs = qs.filter(email_domicile__icontains=q)
        else:
            qs = qs.filter(Q(nom__icontains=q) | Q(prenom__icontains=q) |
                           Q(ifu__icontains=q) | Q(npi__icontains=q) |
                           Q(email_domicile__icontains=q))
        resultats = qs[:20]
    return render(request, 'huissiers/rechercher_justiciable.html', {
        'resultats': resultats, 'q': q, 'filtre': filtre
    })


@login_required
@huissier_required
def liste_significations(request):
    from django.core.paginator import Paginator
    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    statut = request.GET.get('statut', '')
    periode = request.GET.get('periode', '')
    qs = Signification.objects.filter(huissier=huissier).select_related('justiciable')
    if statut:
        qs = qs.filter(statut=statut)
    if periode:
        from django.utils import timezone
        from datetime import timedelta, date
        now = timezone.now()
        today = now.date()
        if periode == 'semaine':
            debut = today - timedelta(days=today.weekday())  # lundi de cette semaine
            qs = qs.filter(date_envoi__date__gte=debut)
        elif periode == 'mois':
            qs = qs.filter(date_envoi__year=today.year, date_envoi__month=today.month)
        elif periode == 'mois_dernier':
            if today.month == 1:
                qs = qs.filter(date_envoi__year=today.year - 1, date_envoi__month=12)
            else:
                qs = qs.filter(date_envoi__year=today.year, date_envoi__month=today.month - 1)
        elif periode == 'trimestre':
            debut = today - timedelta(days=90)
            qs = qs.filter(date_envoi__date__gte=debut)
        elif periode == 'annee':
            qs = qs.filter(date_envoi__year=today.year)
        elif periode == 'annee_derniere':
            qs = qs.filter(date_envoi__year=today.year - 1)
    paginator = Paginator(qs.order_by('-date_envoi'), 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'huissiers/liste_significations.html', {
        'significations': page_obj,
        'page_obj': page_obj,
        'params_str': params.urlencode(),
        'statut_filtre': statut, 'periode': periode,
        'STATUTS': Signification.STATUT_CHOICES,
    })


@login_required
@huissier_required
def inviter_justiciable(request):
    from django.contrib import messages
    from justiciables.models import InvitationJusticiable
    from django.utils import timezone

    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)

    if request.method == 'POST':
        email = escape(request.POST.get('email', '').strip().lower())
        prenom = escape(request.POST.get('prenom', '').strip())
        nom = escape(request.POST.get('nom', '').strip())

        if not email:
            messages.error(request, "L'adresse email est requise.")
            return redirect(request.path)

        # Vérifier si une invitation active existe déjà pour cet email et cet huissier
        invitation_active = InvitationJusticiable.objects.filter(
            huissier=huissier,
            email_cible=email,
            utilise=False,
            date_expiration__gt=timezone.now(),
        ).first()
        if invitation_active:
            messages.warning(request, f"Une invitation active a déjà été envoyée à {email} et n'a pas encore expiré.")
            return redirect(request.path)

        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        from notifications.service import envoyer_invitation_justiciable
        from datetime import timedelta

        token_brut, token_hache = creer_token_activation(
            email, TokenActivation.INVITATION_JUSTICIABLE,
            {'huissier_uuid': str(huissier.uuid), 'prenom': prenom, 'nom': nom},
            heures=72
        )
        InvitationJusticiable.objects.create(
            huissier=huissier,
            email_cible=email,
            token=token_hache,
            date_expiration=timezone.now() + timedelta(hours=72),
        )
        envoyer_invitation_justiciable(email, huissier, token_brut)
        from securite.audit import journaliser
        journaliser(request.user, 'invitation_justiciable_envoyee', 'InvitationJusticiable',
                    '', description=f"Email : {email}", request=request)
        messages.success(request, f"Invitation envoyée à {email}. Le lien est valable 72 heures.")
        return redirect('huissiers:inviter')

    # Historique des invitations de cet huissier (paginé 20/page)
    from django.core.paginator import Paginator
    qs_inv = InvitationJusticiable.objects.filter(
        huissier=huissier
    ).order_by('-date_envoi').select_related('justiciable_cree__user')
    paginator = Paginator(qs_inv, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)

    now = timezone.now()
    return render(request, 'huissiers/inviter_justiciable.html', {
        'huissier': huissier,
        'invitations': page_obj,
        'page_obj': page_obj,
        'params_str': params.urlencode(),
        'now': now,
    })


@login_required
@huissier_required
@require_http_methods(["POST"])
def renvoyer_invitation_justiciable(request, uuid):
    from django.contrib import messages
    from justiciables.models import InvitationJusticiable
    from django.utils import timezone
    from datetime import timedelta

    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    invitation = get_object_or_404(InvitationJusticiable, uuid=uuid, huissier=huissier)

    if invitation.utilise:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Cette invitation a déjà été utilisée.'}, status=400)
        messages.error(request, "Cette invitation a déjà été utilisée.")
        return redirect('huissiers:inviter')

    try:
        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        from notifications.service import envoyer_invitation_justiciable

        token_brut, token_hache = creer_token_activation(
            invitation.email_cible, TokenActivation.INVITATION_JUSTICIABLE,
            {'huissier_uuid': str(huissier.uuid)}, heures=72
        )
        invitation.token = token_hache
        invitation.date_expiration = timezone.now() + timedelta(hours=72)
        invitation.save(update_fields=['token', 'date_expiration'])

        envoyer_invitation_justiciable(invitation.email_cible, huissier, token_brut)
        from securite.audit import journaliser
        journaliser(request.user, 'invitation_justiciable_renvoyee', 'InvitationJusticiable',
                    invitation.uuid, description=f"Email : {invitation.email_cible}", request=request)

        if is_ajax:
            return JsonResponse({
                'success': True,
                'message': f"Invitation renvoyée à {invitation.email_cible}.",
                'nouvelle_expiration': (timezone.now() + timedelta(hours=72)).strftime('%d/%m/%Y %H:%M'),
            })
        messages.success(request, f"Invitation renvoyée à {invitation.email_cible}.")
    except Exception as e:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        messages.error(request, "Erreur lors du renvoi de l'invitation.")

    return redirect('huissiers:inviter')


# ── Gestion des clercs ──────────────────────────────────────────────────────

@login_required
@huissier_required
def liste_clercs(request):
    """Liste des clercs de l'étude — accessible uniquement à l'huissier titulaire."""
    from django.core.paginator import Paginator
    if request.user.role != User.HUISSIER:
        raise Http404
    huissier = request.user.profil_huissier
    from .models import ProfilClerc
    qs = ProfilClerc.objects.filter(huissier=huissier).select_related('user').order_by('nom', 'prenom')
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'huissiers/liste_clercs.html', {
        'huissier': huissier,
        'clercs': page_obj,
        'page_obj': page_obj,
        'params_str': params.urlencode(),
    })


@login_required
@require_http_methods(["POST"])
def inviter_clerc(request):
    """Envoie un lien d'activation à un futur clerc. Huissier titulaire uniquement."""
    if not request.user.is_authenticated or request.user.role != User.HUISSIER:
        raise Http404
    from django.contrib import messages
    from accounts.models import TokenActivation
    from securite.tokens import creer_token_activation
    from securite.audit import journaliser
    from django.utils import timezone as tz

    huissier = request.user.profil_huissier
    email = request.POST.get('email', '').strip().lower()
    prenom = request.POST.get('prenom', '').strip()
    nom = request.POST.get('nom', '').strip()
    telephone = request.POST.get('telephone', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    if not email or '@' not in email:
        if is_ajax:
            return JsonResponse({'success': False, 'error': "Email invalide."}, status=400)
        messages.error(request, "Email invalide.")
        return redirect('huissiers:liste_clercs')

    existing = User.objects.filter(email=email).first()
    if existing:
        msg = "Un compte existe déjà avec cet email."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.error(request, msg)
        return redirect('huissiers:liste_clercs')

    token_actif = TokenActivation.objects.filter(
        email=email,
        type_token=TokenActivation.ACTIVATION_CLERC,
        utilise=False,
        date_expiration__gt=tz.now(),
    ).first()
    if token_actif:
        msg = "Une invitation active existe déjà pour cet email."
        if is_ajax:
            return JsonResponse({'success': False, 'error': msg}, status=400)
        messages.warning(request, msg)
        return redirect('huissiers:liste_clercs')

    try:
        token_brut, _ = creer_token_activation(
            email, TokenActivation.ACTIVATION_CLERC,
            {'huissier_uuid': str(huissier.uuid), 'prenom': prenom, 'nom': nom, 'telephone': telephone},
            heures=72
        )

        from django.core.mail import send_mail
        from django.conf import settings
        from django.urls import reverse
        lien = request.build_absolute_uri(
            reverse('accounts:inscription_clerc') + f'?token={token_brut}'
        )
        corps = (
            f"Bonjour {prenom} {nom},\n\n"
            f"Me {huissier.prenom} {huissier.nom} vous invite à rejoindre l'étude "
            f"« {huissier.nom_etude} » sur e-Signification Bénin en tant que clerc assermenté.\n\n"
            f"Cliquez sur le lien ci-dessous pour créer votre compte (valable 72 heures) :\n{lien}\n\n"
            f"Si vous n'attendiez pas cet email, ignorez ce message.\n\n"
            f"e-Signification Bénin"
        )
        send_mail(
            subject="Invitation — Accès clerc e-Signification Bénin",
            message=corps,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@esignification.bj'),
            recipient_list=[email],
            fail_silently=False,
        )

        journaliser(request.user, 'invitation_clerc_envoyee', 'TokenActivation',
                    '', description=f"Email : {email}", request=request)

        if is_ajax:
            return JsonResponse({'success': True, 'message': f"Invitation envoyée à {email}."})
        messages.success(request, f"Invitation envoyée à {email}. Lien valable 72 heures.")
    except Exception as exc:
        if is_ajax:
            return JsonResponse({'success': False, 'error': str(exc)}, status=500)
        messages.error(request, "Erreur lors de l'envoi de l'invitation.")

    return redirect('huissiers:liste_clercs')


@login_required
@require_http_methods(["POST"])
def desactiver_clerc(request, uuid):
    """Active/désactive un clerc de l'étude. Huissier titulaire uniquement."""
    if not request.user.is_authenticated or request.user.role != User.HUISSIER:
        raise Http404
    from .models import ProfilClerc
    from securite.audit import journaliser
    from django.contrib import messages

    huissier = request.user.profil_huissier
    clerc = get_object_or_404(ProfilClerc, uuid=uuid, huissier=huissier)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    clerc.actif = not clerc.actif
    clerc.save(update_fields=['actif'])
    clerc.user.is_active = clerc.actif
    clerc.user.save(update_fields=['is_active'])

    action = 'clerc_active' if clerc.actif else 'clerc_desactive'
    journaliser(request.user, action, 'ProfilClerc', clerc.uuid, request=request)

    if is_ajax:
        return JsonResponse({
            'success': True,
            'actif': clerc.actif,
            'message': f"{clerc.prenom} {clerc.nom} {'activé' if clerc.actif else 'désactivé'}.",
        })
    msg = f"Clerc {'activé' if clerc.actif else 'désactivé'} : {clerc.prenom} {clerc.nom}."
    messages.success(request, msg)
    return redirect('huissiers:liste_clercs')


# ─── Demandes de modification de profil justiciable ───────────────────────────

@login_required
@huissier_required
def liste_demandes_modification(request):
    """Liste des demandes de modification envoyées à cet huissier."""
    from justiciables.models import DemandeModificationProfil
    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    statut_filtre = request.GET.get('statut', 'en_attente')
    demandes = DemandeModificationProfil.objects.filter(
        huissier=huissier
    ).select_related('justiciable').order_by('-date_creation')
    if statut_filtre in ('en_attente', 'validee', 'refusee'):
        demandes = demandes.filter(statut=statut_filtre)
    nb_en_attente = DemandeModificationProfil.objects.filter(
        huissier=huissier, statut='en_attente'
    ).count()
    from django.core.paginator import Paginator
    paginator = Paginator(demandes, 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'huissiers/liste_demandes_modification.html', {
        'demandes': page_obj,
        'page_obj': page_obj,
        'params_str': params.urlencode(),
        'statut_filtre': statut_filtre,
        'nb_en_attente': nb_en_attente,
    })


@login_required
@huissier_required
def traiter_demande_modification(request, uuid):
    """Affiche le détail d'une demande et permet de la valider ou refuser."""
    from justiciables.models import DemandeModificationProfil
    from securite.chiffrement import dechiffrer_fichier
    from django.utils import timezone as tz
    from django.contrib import messages
    from django.http import HttpResponse

    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    demande = get_object_or_404(DemandeModificationProfil, uuid=uuid, huissier=huissier)

    # Téléchargement d'une pièce justificative
    if request.method == 'GET' and request.GET.get('dl'):
        piece_num = request.GET.get('dl')
        chiffre = getattr(demande, f'piece_{piece_num}_chiffree', None)
        nom = getattr(demande, f'piece_{piece_num}_nom', 'piece.pdf')
        if not chiffre:
            raise Http404
        contenu = dechiffrer_fichier(bytes(chiffre))
        from securite.audit import journaliser as _j
        _j(request.user, 'piece_modification_telechargee', 'DemandeModificationProfil',
           demande.uuid, request=request)
        response = HttpResponse(contenu, content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{nom}"'
        return response

    if request.method == 'POST':
        if demande.statut != DemandeModificationProfil.STATUT_EN_ATTENTE:
            messages.error(request, "Cette demande a déjà été traitée.")
            return redirect('huissiers:liste_demandes_modification')

        action = request.POST.get('action')

        if action == 'valider':
            profil = demande.justiciable
            # Appliquer uniquement les champs renseignés
            if demande.nouveau_nom:
                profil.nom = demande.nouveau_nom
            if demande.nouveau_prenom:
                profil.prenom = demande.nouveau_prenom
            if demande.nouveau_nom_entreprise:
                profil.nom_entreprise = demande.nouveau_nom_entreprise
            if demande.nouveau_telephone:
                profil.telephone = demande.nouveau_telephone
            if demande.nouvelle_adresse:
                profil.adresse = demande.nouvelle_adresse
            if demande.nouveau_ifu:
                profil.ifu = demande.nouveau_ifu
            if demande.nouveau_npi:
                profil.npi = demande.nouveau_npi
            profil.save()

            demande.statut = DemandeModificationProfil.STATUT_VALIDEE
            demande.date_traitement = tz.now()
            demande.save(update_fields=['statut', 'date_traitement'])

            from securite.audit import journaliser as _j
            _j(request.user, 'demande_modification_validee', 'DemandeModificationProfil',
               demande.uuid, request=request)

            # Notifier le justiciable
            try:
                from notifications.service import envoyer_email
                corps = (f"<p>Votre demande de modification de vos informations personnelles "
                         f"a été <strong>validée</strong> par Me {huissier.prenom} {huissier.nom}.</p>"
                         f"<p>Vos informations ont été mises à jour.</p>")
                envoyer_email(demande.justiciable.user.email,
                              "Demande de modification — Validée", corps)
            except Exception:
                pass

            messages.success(request, "Demande validée. Les informations du justiciable ont été mises à jour.")

        elif action == 'refuser':
            motif = escape(request.POST.get('motif_refus', '').strip())
            if not motif:
                messages.error(request, "Le motif de refus est obligatoire.")
                return redirect('huissiers:traiter_demande_modification', uuid=uuid)

            demande.statut = DemandeModificationProfil.STATUT_REFUSEE
            demande.motif_refus = motif
            demande.date_traitement = tz.now()
            demande.save(update_fields=['statut', 'motif_refus', 'date_traitement'])

            from securite.audit import journaliser as _j
            _j(request.user, 'demande_modification_refusee', 'DemandeModificationProfil',
               demande.uuid, request=request)

            try:
                from notifications.service import envoyer_email
                corps = (
                    f"<p>Votre demande de modification de vos informations personnelles "
                    f"a été <strong>refusée</strong> par l'huissier "
                    f"<strong>Me {demande.huissier.nom_complet}</strong>.</p>"
                    f"<p><strong>Motif :</strong> {motif}</p>"
                )
                envoyer_email(
                    demande.justiciable.email_domicile,
                    "Demande de modification — Refusée", corps)
            except Exception:
                pass
            messages.success(request, "Demande refusée. Le justiciable a été notifié.")

        return redirect('huissiers:liste_demandes_modification')

    return render(request, 'huissiers/traiter_demande_modification.html', {'demande': demande})


# ─── Paramètres signatures ────────────────────────────────────────────────────

@login_required
@huissier_required
def parametres_signatures(request):
    """Gestion des 3 signatures/cachets de l'huissier."""
    from accounts.models import User as _User
    huissier = (request.user.profil_huissier if request.user.role == _User.HUISSIER
                else request.user.profil_clerc.huissier)
    from .models import ParametreSignatureHuissier
    params, _ = ParametreSignatureHuissier.objects.get_or_create(huissier=huissier)

    PREFIXES_IMAGE_VALIDES = (
        'data:image/png;base64,',
        'data:image/jpeg;base64,',
        'data:image/jpg;base64,',
        'data:image/svg+xml;base64,',
        'data:image/webp;base64,',
        'data:image/gif;base64,',
    )

    def _valider_b64(valeur):
        return valeur and any(valeur.startswith(p) for p in PREFIXES_IMAGE_VALIDES)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'enregistrer_signature_simple':
            b64 = request.POST.get('sig_simple_b64', '').strip()
            label = escape(request.POST.get('sig_simple_label', '').strip()) or 'Signature simple'
            if _valider_b64(b64):
                params.signature_simple_b64 = b64
                params.signature_simple_label = label[:80]
                params.save(update_fields=['signature_simple_b64', 'signature_simple_label'])
                from django.contrib import messages
                messages.success(request, "Signature simple enregistrée.")
            else:
                from django.contrib import messages
                messages.error(request, "Signature invalide — veuillez dessiner ou importer une image.")

        elif action == 'enregistrer_signature_cachet':
            b64 = request.POST.get('sig_cachet_b64', '').strip()
            label = escape(request.POST.get('sig_cachet_label', '').strip()) or 'Signature avec cachet'
            if _valider_b64(b64):
                params.signature_cachet_b64 = b64
                params.signature_cachet_label = label[:80]
                params.save(update_fields=['signature_cachet_b64', 'signature_cachet_label'])
                from django.contrib import messages
                messages.success(request, "Signature avec cachet enregistrée.")
            else:
                from django.contrib import messages
                messages.error(request, "Signature invalide — veuillez dessiner ou importer une image.")

        elif action == 'enregistrer_cachet_simple':
            b64 = request.POST.get('cachet_simple_b64', '').strip()
            label = escape(request.POST.get('cachet_simple_label', '').strip()) or 'Cachet simple'
            if _valider_b64(b64):
                params.cachet_simple_b64 = b64
                params.cachet_simple_label = label[:80]
                params.save(update_fields=['cachet_simple_b64', 'cachet_simple_label'])
                from django.contrib import messages
                messages.success(request, "Cachet simple enregistré.")
            else:
                from django.contrib import messages
                messages.error(request, "Cachet invalide — veuillez dessiner ou importer une image.")

        elif action in ('effacer_signature_simple', 'effacer_signature_cachet', 'effacer_cachet_simple'):
            champ_map = {
                'effacer_signature_simple': ('signature_simple_b64',),
                'effacer_signature_cachet': ('signature_cachet_b64',),
                'effacer_cachet_simple':    ('cachet_simple_b64',),
            }
            champ = champ_map[action][0]
            setattr(params, champ, '')
            params.save(update_fields=[champ])
            from django.contrib import messages
            messages.success(request, "Supprimé.")

        return redirect('huissiers:parametres_signatures')

    return render(request, 'huissiers/parametres_signatures.html', {
        'huissier': huissier,
        'params': params,
    })
