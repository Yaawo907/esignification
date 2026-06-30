from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404
from accounts.models import User
from significations.models import Signification, ReponseJusticiable
from securite.audit import journaliser
from securite.chiffrement import chiffrer_fichier, hash_fichier
from django.utils.html import escape
from django.utils import timezone


def justiciable_required(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or request.user.role != User.JUSTICIABLE:
            return redirect(f'/connexion/?next={request.path}')
        return view_func(request, *args, **kwargs)
    return wrapped


@login_required
@justiciable_required
def tableau_de_bord(request):
    profil = request.user.profil_justiciable
    significations = Signification.objects.filter(justiciable=profil)
    stats = {
        'recues': significations.count(),
        'en_attente': significations.filter(statut='en_attente').count(),
        'acceptees': significations.filter(statut__in=['acceptee', 'repondu']).count(),
        'reponses_envoyees': ReponseJusticiable.objects.filter(signification__justiciable=profil).count(),
    }
    recentes = significations.order_by('-date_envoi')[:10]
    sig_acceptee_ref = request.session.pop('sig_acceptee_ref', None)
    return render(request, 'justiciables/tableau_de_bord.html', {
        'profil': profil, 'stats': stats, 'significations_recentes': recentes,
        'sig_acceptee_ref': sig_acceptee_ref,
    })


@login_required
@justiciable_required
def liste_significations(request):
    from django.core.paginator import Paginator
    profil = request.user.profil_justiciable
    statut = request.GET.get('statut', 'en_attente')
    periode = request.GET.get('periode', '')
    qs = Signification.objects.filter(justiciable=profil).select_related('huissier')
    if statut and statut != 'toutes':
        qs = qs.filter(statut=statut)
    if periode:
        from datetime import timedelta, date
        today = timezone.now().date()
        if periode == 'semaine':
            from datetime import timedelta
            qs = qs.filter(date_envoi__date__gte=today - timedelta(days=today.weekday()))
        elif periode == 'mois':
            qs = qs.filter(date_envoi__year=today.year, date_envoi__month=today.month)
        elif periode == 'mois_dernier':
            if today.month == 1:
                qs = qs.filter(date_envoi__year=today.year - 1, date_envoi__month=12)
            else:
                qs = qs.filter(date_envoi__year=today.year, date_envoi__month=today.month - 1)
        elif periode == 'trimestre':
            qs = qs.filter(date_envoi__date__gte=today - timedelta(days=90))
        elif periode == 'annee':
            qs = qs.filter(date_envoi__year=today.year)
        elif periode == 'annee_derniere':
            qs = qs.filter(date_envoi__year=today.year - 1)
    paginator = Paginator(qs.order_by('-date_envoi'), 20)
    page_obj = paginator.get_page(request.GET.get('page', 1))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'justiciables/liste_significations.html', {
        'significations': page_obj,
        'page_obj': page_obj,
        'params_str': params.urlencode(),
        'statut_filtre': statut, 'periode': periode,
    })


@login_required
@justiciable_required
def profil(request):
    from django.contrib import messages
    from accounts.forms import ModificationMotDePasseForm
    from accounts.mfa_profil import contexte_mfa_profil, traiter_action_mfa_profil

    profil = request.user.profil_justiciable
    user = request.user
    form_mdp = ModificationMotDePasseForm(user=user)
    erreur_email = None
    succes_email = False

    if request.method == 'POST' and 'action' in request.POST:
        action = request.POST.get('action')

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

        elif action == 'changer_email':
            nouveau_email = escape(request.POST.get('nouveau_email', '').strip().lower())
            if not nouveau_email:
                erreur_email = "L'adresse email est obligatoire."
            elif nouveau_email == user.email.lower():
                erreur_email = "C'est déjà votre adresse email actuelle."
            else:
                from accounts.models import User as U
                if U.objects.filter(email=nouveau_email).exclude(pk=user.pk).exists():
                    erreur_email = "Cette adresse email est déjà associée à un compte."
                else:
                    _envoyer_confirmation_changement_email(user, nouveau_email)
                    journaliser(user, 'demande_changement_email_domicile',
                                description=f"Nouveau email : {nouveau_email}", request=request)
                    succes_email = True
        else:
            mfa_redirect = traiter_action_mfa_profil(
                request, user, 'justiciables:profil', telephone=profil.telephone,
            )
            if mfa_redirect:
                return mfa_redirect

    user.refresh_from_db(fields=['mfa_methode', 'totp_secret'])

    return render(request, 'justiciables/profil.html', {
        'profil': profil,
        'form_mdp': form_mdp,
        'erreur_email': erreur_email,
        'succes_email': succes_email,
        **contexte_mfa_profil(user, request.session),
    })


def _envoyer_confirmation_changement_email(user, nouveau_email):
    """Envoie un lien de confirmation au nouveau email pour valider le changement de domicile."""
    from django.conf import settings
    from securite.tokens import creer_token_activation
    from accounts.models import TokenActivation
    from notifications.service import envoyer_email

    token_brut, _ = creer_token_activation(
        nouveau_email,
        TokenActivation.CHANGEMENT_EMAIL_DOMICILE,
        {'user_id': user.pk, 'nouveau_email': nouveau_email, 'ancien_email': user.email},
        heures=24,
    )
    lien = f"{settings.SITE_URL}/justiciable/confirmer-email/?token={token_brut}"

    # Email au NOUVEAU domicile
    corps_nouveau = f"""
    <div style="font-family:Arial,sans-serif;padding:24px;">
      <h2 style="color:#134e3a;">Confirmation de votre nouveau domicile électronique</h2>
      <p>Vous avez demandé à changer votre domicile électronique sur la plateforme e-Signification Bénin.</p>
      <p>Cliquez sur le lien ci-dessous pour confirmer cette nouvelle adresse :</p>
      <p style="margin:20px 0;">
        <a href="{lien}"
           style="background:#134e3a;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;">
          Confirmer mon nouveau domicile électronique
        </a>
      </p>
      <p style="color:#888;font-size:13px;">Ce lien est valable 24 heures. Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.</p>
    </div>"""
    envoyer_email(nouveau_email, "Confirmez votre nouveau domicile électronique — e-Signification Bénin", corps_nouveau)

    # Notification à l'ANCIEN email
    corps_ancien = f"""
    <div style="font-family:Arial,sans-serif;padding:24px;">
      <h2 style="color:#134e3a;">Demande de changement de domicile électronique</h2>
      <p>Une demande de changement de votre domicile électronique a été initiée sur la plateforme e-Signification Bénin.</p>
      <p>Le nouveau domicile demandé est : <strong>{nouveau_email}</strong></p>
      <p style="color:#888;font-size:13px;">Si vous n'êtes pas à l'origine de cette demande, contactez immédiatement l'administrateur de la plateforme.</p>
    </div>"""
    envoyer_email(user.email, "Alerte : demande de changement de domicile électronique", corps_ancien)


def confirmer_changement_email(request):
    """Confirme le changement d'email domicile via le lien reçu dans le nouveau email."""
    from django.contrib import messages
    from securite.tokens import valider_token, marquer_token_utilise
    from accounts.models import TokenActivation, User as U

    token_brut = request.GET.get('token', '')
    token_obj, erreur = valider_token(token_brut, TokenActivation.CHANGEMENT_EMAIL_DOMICILE)
    if erreur:
        return render(request, 'accounts/token_invalide.html', {'erreur': erreur})

    user_id = token_obj.metadata.get('user_id')
    nouveau_email = token_obj.metadata.get('nouveau_email', '').strip().lower()

    if not user_id or not nouveau_email:
        return render(request, 'accounts/token_invalide.html', {'erreur': 'Token invalide.'})

    try:
        user = U.objects.get(pk=user_id)
    except U.DoesNotExist:
        return render(request, 'accounts/token_invalide.html', {'erreur': 'Compte introuvable.'})

    # Vérifier que le nouveau email n'est pas déjà pris
    if U.objects.filter(email=nouveau_email).exclude(pk=user.pk).exists():
        return render(request, 'accounts/token_invalide.html', {
            'erreur': 'Cette adresse email est déjà utilisée par un autre compte.'
        })

    ancien_email = user.email

    # Mettre à jour User et ProfilJusticiable
    user.email = nouveau_email
    user.save(update_fields=['email'])

    profil = user.profil_justiciable
    profil.email_domicile = nouveau_email
    profil.email_domicile_verifie = True
    profil.save(update_fields=['email_domicile', 'email_domicile_verifie'])

    marquer_token_utilise(token_obj)
    journaliser(user, 'changement_email_domicile_confirme',
                description=f"{ancien_email} → {nouveau_email}", request=request)

    messages.success(request, f"Votre domicile électronique a été mis à jour : {nouveau_email}")
    return redirect('/connexion/')


@login_required
@justiciable_required
def envoyer_reponse(request, uuid):
    import hashlib
    from django.contrib import messages
    from notifications.service import envoyer_reponse_huissier
    from significations.pdf_reponse import generer_pdf_reponse, fusionner_annexe_pdf

    profil = request.user.profil_justiciable
    sig = get_object_or_404(Signification, uuid=uuid, justiciable=profil)
    if not sig.necessite_reponse or sig.statut not in ['acceptee']:
        raise Http404
    if hasattr(sig, 'reponse'):
        messages.warning(request, "Une réponse a déjà été envoyée pour cette signification.")
        return redirect('justiciables:significations')

    if request.method == 'POST':
        texte = request.POST.get('texte_reponse', '').strip()
        fichier = request.FILES.get('fichier_reponse')
        signature_b64 = request.POST.get('signature_b64', '').strip()

        from significations.pdf_reponse import _signature_b64_valide

        def _ctx_erreur():
            return render(request, 'justiciables/envoyer_reponse.html', {'sig': sig, 'texte_saisi': texte})

        if not texte and not fichier:
            messages.error(request, "Saisissez votre réponse ou joignez un document PDF.")
            return _ctx_erreur()

        if texte and len(texte) < 10:
            messages.error(request, "Votre réponse doit contenir au moins 10 caractères.")
            return _ctx_erreur()

        if texte and not _signature_b64_valide(signature_b64):
            messages.error(request, "Veuillez apposer votre signature (pad ou import d'image) avant d'envoyer.")
            return _ctx_erreur()

        if signature_b64:
            import base64
            try:
                sig_bytes = base64.b64decode(signature_b64.split(',', 1)[1])
                if len(sig_bytes) > 500 * 1024:
                    messages.error(request, "L'image de signature ne doit pas dépasser 500 Ko.")
                    return _ctx_erreur()
            except Exception:
                messages.error(request, "Signature invalide — veuillez dessiner ou importer une image.")
                return _ctx_erreur()

        annexe_bytes = None
        annexe_nom = ''
        annexe_hash = ''
        if fichier:
            if not fichier.name.lower().endswith('.pdf'):
                messages.error(request, "Seuls les fichiers PDF sont acceptés en annexe.")
                return _ctx_erreur()
            annexe_bytes = fichier.read()
            if len(annexe_bytes) > 20 * 1024 * 1024:
                messages.error(request, "L'annexe ne doit pas dépasser 20 Mo.")
                return _ctx_erreur()
            annexe_nom = escape(fichier.name)
            annexe_hash = hash_fichier(annexe_bytes)

        hash_contenu = hashlib.sha256(texte.encode('utf-8')).hexdigest() if texte else ''

        reponse = ReponseJusticiable(
            signification=sig,
            hash_contenu=hash_contenu,
            nom_fichier_annexe=annexe_nom,
            hash_annexe=annexe_hash,
            signature_justiciable_b64=signature_b64 if texte else '',
        )
        if texte:
            reponse.enregistrer_texte(texte)
        reponse.save()

        pdf_bytes = None
        if texte:
            pdf_bytes = generer_pdf_reponse(
                sig, reponse, texte,
                annexe_nom=annexe_nom, annexe_hash=annexe_hash,
            )
            if annexe_bytes:
                pdf_bytes = fusionner_annexe_pdf(pdf_bytes, annexe_bytes)
            reponse.fichier_reponse_chiffre = chiffrer_fichier(pdf_bytes)
            reponse.nom_fichier_reponse = f"reponse_{sig.reference}.pdf"
            reponse.hash_reponse = hash_fichier(pdf_bytes)
            reponse.save(update_fields=[
                'fichier_reponse_chiffre', 'nom_fichier_reponse', 'hash_reponse',
            ])
        elif annexe_bytes:
            reponse.fichier_reponse_chiffre = chiffrer_fichier(annexe_bytes)
            reponse.nom_fichier_reponse = annexe_nom
            reponse.hash_reponse = hash_fichier(annexe_bytes)
            reponse.save(update_fields=[
                'fichier_reponse_chiffre', 'nom_fichier_reponse', 'hash_reponse',
            ])
            pdf_bytes = annexe_bytes

        sig.statut = Signification.STATUT_REPONDU
        sig.save(update_fields=['statut'])

        if pdf_bytes:
            envoyer_reponse_huissier(sig, reponse, pdf_bytes)
        journaliser(request.user, 'reponse_envoyee', 'Signification', sig.uuid, request=request)

        if texte:
            msg = "Votre réponse a été convertie en PDF officiel et transmise à l'huissier."
            if annexe_nom:
                msg += f" L'annexe « {annexe_nom} » a été fusionnée au document."
            messages.success(request, msg)
        else:
            messages.success(request, "Votre réponse a été envoyée à l'huissier.")
        return redirect('justiciables:tableau_de_bord')

    return render(request, 'justiciables/envoyer_reponse.html', {'sig': sig})


# ─── Demande de modification de profil ────────────────────────────────────────

@login_required
@justiciable_required
def demander_modification_profil(request):
    from .models import DemandeModificationProfil
    from huissiers.models import ProfilHuissier
    from securite.chiffrement import chiffrer_fichier
    from django.contrib import messages as msg

    profil = request.user.profil_justiciable

    # Vérifier qu'il n'y a pas déjà une demande en attente
    demande_en_cours = DemandeModificationProfil.objects.filter(
        justiciable=profil, statut=DemandeModificationProfil.STATUT_EN_ATTENTE
    ).first()

    if request.method == 'POST':
        if demande_en_cours:
            msg.error(request, "Vous avez déjà une demande en cours. Attendez sa résolution avant d'en soumettre une nouvelle.")
            return redirect('justiciables:demander_modification')

        # Recherche de l'huissier par UUID
        huissier_uuid = request.POST.get('huissier_uuid', '').strip()
        huissier = None
        if huissier_uuid:
            try:
                import uuid as _uuid
                huissier = ProfilHuissier.objects.get(uuid=_uuid.UUID(huissier_uuid))
            except (ProfilHuissier.DoesNotExist, ValueError):
                msg.error(request, "Huissier introuvable. Veuillez sélectionner un huissier valide.")
                return redirect('justiciables:demander_modification')
        else:
            msg.error(request, "Veuillez sélectionner un huissier destinataire.")
            return redirect('justiciables:demander_modification')

        demande = DemandeModificationProfil(
            justiciable=profil,
            huissier=huissier,
            nouveau_nom=escape(request.POST.get('nouveau_nom', '').strip()),
            nouveau_prenom=escape(request.POST.get('nouveau_prenom', '').strip()),
            nouveau_nom_entreprise=escape(request.POST.get('nouveau_nom_entreprise', '').strip()),
            nouveau_telephone=escape(request.POST.get('nouveau_telephone', '').strip()),
            nouvelle_adresse=escape(request.POST.get('nouvelle_adresse', '').strip()),
            nouveau_ifu=escape(request.POST.get('nouveau_ifu', '').strip()),
            nouveau_npi=escape(request.POST.get('nouveau_npi', '').strip()),
            message_justiciable=escape(request.POST.get('message_justiciable', '').strip()),
        )

        # Pièces justificatives — chiffrées avant stockage
        for idx, champ in [('1', 'piece_1'), ('2', 'piece_2')]:
            fichier = request.FILES.get(f'piece_{idx}')
            if fichier:
                if fichier.size > 5 * 1024 * 1024:
                    msg.error(request, f"La pièce {idx} dépasse 5 Mo.")
                    return redirect('justiciables:demander_modification')
                contenu = fichier.read()
                setattr(demande, f'{champ}_chiffree', chiffrer_fichier(contenu))
                setattr(demande, f'{champ}_nom', escape(fichier.name))

        # Vérifier qu'au moins un champ est modifié
        champs_remplis = [
            demande.nouveau_nom, demande.nouveau_prenom, demande.nouveau_nom_entreprise,
            demande.nouveau_telephone, demande.nouvelle_adresse, demande.nouveau_ifu, demande.nouveau_npi,
        ]
        if not any(champs_remplis):
            msg.error(request, "Veuillez renseigner au moins un champ à modifier.")
            return redirect('justiciables:demander_modification')

        demande.save()

        # Notifier l'huissier par email
        try:
            from notifications.service import envoyer_email
            corps = (
                f"<p>Le justiciable <strong>{profil.nom_complet}</strong> "
                f"(<em>{profil.email_domicile}</em>) a soumis une demande de modification "
                f"de ses informations personnelles.</p>"
                f"<p>Connectez-vous pour consulter et traiter cette demande.</p>"
            )
            envoyer_email(huissier.user.email,
                          f"Demande de modification de profil — {profil.nom_complet}", corps)
        except Exception:
            pass  # Ne pas bloquer si l'email échoue

        journaliser(request.user, 'demande_modification_profil_soumise',
                    'DemandeModificationProfil', demande.uuid, request=request)
        msg.success(request, "Votre demande a été envoyée à l'huissier. Vous serez notifié de sa décision.")
        return redirect('justiciables:profil')

    # GET : charger la liste des huissiers actifs + recherche
    q = escape(request.GET.get('q', '').strip())
    huissiers = ProfilHuissier.objects.filter(user__is_active=True).order_by('nom')
    if q and len(q) >= 2:
        from django.db.models import Q
        huissiers = huissiers.filter(
            Q(nom__icontains=q) | Q(prenom__icontains=q) | Q(nom_etude__icontains=q)
        )

    return render(request, 'justiciables/demander_modification.html', {
        'profil': profil,
        'demande_en_cours': demande_en_cours,
        'huissiers': huissiers[:20],
        'q': q,
    })
