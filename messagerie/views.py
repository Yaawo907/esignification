from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404, HttpResponse
from django.utils.html import escape
from django.utils import timezone
from django.db.models import Q
from django.views.decorators.http import require_POST

from accounts.models import User
from securite.audit import journaliser
from securite.chiffrement import chiffrer_fichier, dechiffrer_fichier, chiffrer_texte, dechiffrer_texte
from .models import Conversation, Message, PieceJointeMessage

TAILLE_MAX_PJ = 10 * 1024 * 1024  # 10 Mo
TYPES_AUTORISES = {'application/pdf', 'image/png', 'image/jpeg', 'image/jpg',
                   'application/msword',
                   'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
EXTENSIONS_AUTORISEES = {'.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx'}


def _get_conversations(user):
    return Conversation.objects.filter(
        Q(participant_1=user) | Q(participant_2=user)
    ).select_related('participant_1', 'participant_2').order_by('-date_dernier_message')


def _check_extension(nom):
    import os
    _, ext = os.path.splitext(nom.lower())
    return ext in EXTENSIONS_AUTORISEES


def _nom_affichage(user):
    """Nom lisible selon le rôle."""
    try:
        if user.role == User.HUISSIER:
            return f"Me {user.profil_huissier.prenom} {user.profil_huissier.nom}"
        elif user.role == User.CLERC:
            c = user.profil_clerc
            return f"{c.prenom} {c.nom} (clerc)"
        elif user.role == User.JUSTICIABLE:
            return user.profil_justiciable.nom_complet
        elif user.role == User.ADMIN:
            return "Administration"
    except Exception:
        pass
    return user.email


@login_required
def liste_conversations(request):
    user = request.user
    conversations = _get_conversations(user)

    # Exclure les archivées selon le participant
    conv_list = []
    for c in conversations:
        if c.participant_1_id == user.pk and c.archivee_p1:
            continue
        if c.participant_2_id == user.pk and c.archivee_p2:
            continue
        conv_list.append(c)

    # Précomputer non_lus, autre_nom et snippet pour le template
    conv_enrichies = []
    total_non_lus = 0
    for c in conv_list:
        nl = c.non_lus_pour(user)
        total_non_lus += nl
        autre = c.autre_participant(user)
        # Snippet + méta du dernier message
        snippet = ''
        dernier_auteur_moi = False
        a_pj = False
        try:
            dernier = c.messages.select_related('auteur').prefetch_related('pieces_jointes').order_by('-date_envoi').first()
            if dernier:
                texte = dechiffrer_texte(bytes(dernier.contenu_chiffre).decode())
                snippet = texte[:80].replace('\n', ' ')
                if len(texte) > 80:
                    snippet += '…'
                dernier_auteur_moi = (dernier.auteur_id == user.pk)
                a_pj = dernier.pieces_jointes.exists()
        except Exception:
            pass
        conv_enrichies.append({
            'conv': c,
            'autre': autre,
            'autre_nom': _nom_affichage(autre),
            'non_lus': nl,
            'snippet': snippet,
            'dernier_auteur_moi': dernier_auteur_moi,
            'a_pj': a_pj,
        })

    return render(request, 'messagerie/liste_conversations.html', {
        'conversations': conv_enrichies,
        'total_non_lus': total_non_lus,
        'nom_affichage': _nom_affichage(user),
    })


@login_required
def conversation(request, uuid):
    user = request.user
    conv = get_object_or_404(Conversation, uuid=uuid)
    if not conv.is_participant(user):
        raise Http404

    # Marquer les messages reçus comme lus
    conv.messages.filter(lu=False).exclude(auteur=user).update(
        lu=True, date_lecture=timezone.now()
    )

    # Déchiffrer les messages pour l'affichage
    messages_affichage = []
    for msg in conv.messages.select_related('auteur').prefetch_related('pieces_jointes'):
        try:
            contenu = dechiffrer_texte(bytes(msg.contenu_chiffre).decode())
        except Exception:
            contenu = "[Message illisible]"
        messages_affichage.append({
            'obj': msg,
            'contenu': contenu,
            'est_moi': msg.auteur_id == user.pk,
            'pieces': msg.pieces_jointes.all(),
        })

    autre = conv.autre_participant(user)

    return render(request, 'messagerie/conversation.html', {
        'conv': conv,
        'messages_affichage': messages_affichage,
        'autre': autre,
        'autre_nom': _nom_affichage(autre),
        'moi_nom': _nom_affichage(user),
    })


@login_required
@require_POST
def envoyer_message(request, uuid):
    user = request.user
    conv = get_object_or_404(Conversation, uuid=uuid)
    if not conv.is_participant(user):
        return JsonResponse({'success': False, 'error': 'Accès refusé'}, status=403)

    contenu_brut = escape(request.POST.get('contenu', '').strip())
    fichiers = request.FILES.getlist('pieces_jointes')

    if not contenu_brut and not fichiers:
        return JsonResponse({'success': False, 'error': 'Message vide.'}, status=400)

    if len(contenu_brut) > 5000:
        return JsonResponse({'success': False, 'error': 'Message trop long (max 5000 caractères).'}, status=400)

    # Valider les pièces jointes avant création du message
    for f in fichiers:
        if f.size > TAILLE_MAX_PJ:
            return JsonResponse({'success': False,
                                 'error': f'"{f.name}" dépasse 10 Mo.'}, status=400)
        if not _check_extension(f.name):
            return JsonResponse({'success': False,
                                 'error': f'Type de fichier non autorisé : {f.name}'}, status=400)

    # Chiffrer et sauvegarder le message
    contenu_chiffre = chiffrer_texte(contenu_brut).encode()
    msg = Message.objects.create(
        conversation=conv,
        auteur=user,
        contenu_chiffre=contenu_chiffre,
    )

    # Sauvegarder les pièces jointes chiffrées
    for f in fichiers:
        contenu_pj = f.read()
        PieceJointeMessage.objects.create(
            message=msg,
            fichier_chiffre=chiffrer_fichier(contenu_pj),
            nom_fichier=escape(f.name),
            taille_octets=f.size,
            type_mime=f.content_type or '',
        )

    # Mettre à jour la date du dernier message
    conv.date_dernier_message = timezone.now()
    conv.save(update_fields=['date_dernier_message'])

    journaliser(user, 'message_envoye', 'Conversation', conv.uuid, request=request)

    # Notifier l'autre participant par email (non bloquant)
    try:
        autre = conv.autre_participant(user)
        from notifications.service import envoyer_email
        corps = (f"<p>Vous avez reçu un nouveau message de <strong>{_nom_affichage(user)}</strong>"
                 f" dans la conversation : <em>{conv.sujet}</em>.</p>"
                 f"<p>Connectez-vous pour lire et répondre.</p>")
        envoyer_email(autre.email, f"Nouveau message — {conv.sujet}", corps)
    except Exception:
        pass

    # Réponse AJAX avec le message rendu
    try:
        contenu_dechiffre = dechiffrer_texte(bytes(msg.contenu_chiffre).decode())
    except Exception:
        contenu_dechiffre = contenu_brut

    pieces_data = [
        {'uuid': str(pj.uuid), 'nom': pj.nom_fichier, 'taille': pj.taille_lisible}
        for pj in msg.pieces_jointes.all()
    ]

    return JsonResponse({
        'success': True,
        'message': {
            'uuid': str(msg.uuid),
            'contenu': contenu_dechiffre,
            'date': msg.date_envoi.strftime('%d/%m/%Y %H:%M'),
            'est_moi': True,
            'auteur': _nom_affichage(user),
            'pieces': pieces_data,
        }
    })


@login_required
def nouveaux_messages_ajax(request, uuid):
    """Polling AJAX — retourne les messages plus récents qu'un timestamp donné."""
    user = request.user
    conv = get_object_or_404(Conversation, uuid=uuid)
    if not conv.is_participant(user):
        return JsonResponse({'error': 'Accès refusé'}, status=403)

    depuis_str = request.GET.get('depuis', '')
    try:
        from datetime import datetime
        depuis = datetime.fromisoformat(depuis_str)
    except Exception:
        depuis = timezone.now()

    nouveaux = conv.messages.filter(date_envoi__gt=depuis).select_related('auteur').prefetch_related('pieces_jointes')

    # Marquer comme lus
    nouveaux.filter(lu=False).exclude(auteur=user).update(lu=True, date_lecture=timezone.now())

    data = []
    for msg in nouveaux:
        try:
            contenu = dechiffrer_texte(bytes(msg.contenu_chiffre).decode())
        except Exception:
            contenu = "[Message illisible]"
        pieces = [{'uuid': str(pj.uuid), 'nom': pj.nom_fichier, 'taille': pj.taille_lisible}
                  for pj in msg.pieces_jointes.all()]
        data.append({
            'uuid': str(msg.uuid),
            'contenu': contenu,
            'date': msg.date_envoi.strftime('%d/%m/%Y %H:%M'),
            'est_moi': msg.auteur_id == user.pk,
            'auteur': _nom_affichage(msg.auteur) if msg.auteur else '?',
            'pieces': pieces,
        })

    return JsonResponse({'messages': data, 'timestamp': timezone.now().isoformat()})


@login_required
def nouvelle_conversation(request):
    user = request.user

    if request.method == 'POST':
        dest_uuid = request.POST.get('destinataire_uuid', '').strip()
        sujet = escape(request.POST.get('sujet', '').strip())
        contenu_brut = escape(request.POST.get('contenu', '').strip())

        if not dest_uuid or not sujet or not contenu_brut:
            from django.contrib import messages as msg
            msg.error(request, "Tous les champs sont requis.")
            return redirect('messagerie:nouvelle_conversation')

        try:
            import uuid as _uuid
            dest = User.objects.get(uuid=_uuid.UUID(dest_uuid), is_active=True)
        except (User.DoesNotExist, ValueError, AttributeError):
            from django.contrib import messages as msg
            msg.error(request, "Destinataire introuvable.")
            return redirect('messagerie:nouvelle_conversation')

        if dest.pk == user.pk:
            from django.contrib import messages as msg
            msg.error(request, "Vous ne pouvez pas vous envoyer un message.")
            return redirect('messagerie:nouvelle_conversation')

        # Vérifier la combinaison de rôles autorisée
        roles_autorises = {
            User.HUISSIER: [User.HUISSIER, User.JUSTICIABLE, User.ADMIN, User.CLERC],
            User.CLERC:    [User.HUISSIER, User.CLERC, User.JUSTICIABLE],
            User.JUSTICIABLE: [User.HUISSIER, User.CLERC],
            User.ADMIN:    [User.HUISSIER, User.CLERC, User.JUSTICIABLE],
        }
        if dest.role not in roles_autorises.get(user.role, []):
            from django.contrib import messages as msg
            msg.error(request, "Cette combinaison de rôles n'est pas autorisée.")
            return redirect('messagerie:nouvelle_conversation')

        # Créer la conversation
        conv = Conversation.objects.create(
            participant_1=user,
            participant_2=dest,
            sujet=sujet[:255],
        )

        # Premier message
        fichiers = request.FILES.getlist('pieces_jointes')
        for f in fichiers:
            if f.size > TAILLE_MAX_PJ or not _check_extension(f.name):
                conv.delete()
                from django.contrib import messages as msg
                msg.error(request, f"Fichier refusé : {f.name}")
                return redirect('messagerie:nouvelle_conversation')

        contenu_chiffre = chiffrer_texte(contenu_brut).encode()
        premier_msg = Message.objects.create(
            conversation=conv,
            auteur=user,
            contenu_chiffre=contenu_chiffre,
        )
        for f in fichiers:
            contenu_pj = f.read()
            PieceJointeMessage.objects.create(
                message=premier_msg,
                fichier_chiffre=chiffrer_fichier(contenu_pj),
                nom_fichier=escape(f.name),
                taille_octets=f.size,
                type_mime=f.content_type or '',
            )

        journaliser(user, 'conversation_creee', 'Conversation', conv.uuid, request=request)

        try:
            from notifications.service import envoyer_email
            corps = (f"<p><strong>{_nom_affichage(user)}</strong> vous a envoyé un message.</p>"
                     f"<p>Sujet : <em>{sujet}</em></p>"
                     f"<p>Connectez-vous pour lire et répondre.</p>")
            envoyer_email(dest.email, f"Nouveau message — {sujet}", corps)
        except Exception:
            pass

        return redirect('messagerie:conversation', uuid=conv.uuid)

    # GET : charger les destinataires possibles
    q = escape(request.GET.get('q', '').strip())
    destinataires = []
    if q and len(q) >= 2:
        roles_cibles = {
            User.HUISSIER:    [User.HUISSIER, User.JUSTICIABLE, User.ADMIN, User.CLERC],
            User.CLERC:       [User.HUISSIER, User.CLERC, User.JUSTICIABLE],
            User.JUSTICIABLE: [User.HUISSIER, User.CLERC],
            User.ADMIN:       [User.HUISSIER, User.CLERC, User.JUSTICIABLE],
        }.get(user.role, [])

        qs = User.objects.filter(
            role__in=roles_cibles, is_active=True
        ).exclude(pk=user.pk).select_related(
            'profil_huissier', 'profil_justiciable', 'profil_clerc'
        ).filter(
            Q(email__icontains=q)
            | Q(profil_huissier__nom__icontains=q)
            | Q(profil_huissier__prenom__icontains=q)
            | Q(profil_huissier__nom_etude__icontains=q)
            | Q(profil_justiciable__nom__icontains=q)
            | Q(profil_justiciable__prenom__icontains=q)
            | Q(profil_justiciable__nom_entreprise__icontains=q)
            | Q(profil_clerc__nom__icontains=q)
            | Q(profil_clerc__prenom__icontains=q)
        )[:15]

        # Enrichir avec le nom affiché
        dest_enrichis = []
        for d in qs:
            dest_enrichis.append({'user': d, 'nom': _nom_affichage(d)})
        destinataires = dest_enrichis

    return render(request, 'messagerie/nouvelle_conversation.html', {
        'q': q,
        'destinataires': destinataires,
    })


@login_required
def telecharger_piece_jointe(request, uuid):
    """Télécharge une pièce jointe déchiffrée — uniquement pour les participants."""
    user = request.user
    pj = get_object_or_404(PieceJointeMessage, uuid=uuid)
    conv = pj.message.conversation

    if not conv.is_participant(user):
        raise Http404

    contenu = dechiffrer_fichier(bytes(pj.fichier_chiffre))
    journaliser(user, 'piece_jointe_telechargee', 'PieceJointeMessage', pj.uuid, request=request)

    response = HttpResponse(contenu, content_type=pj.type_mime or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{pj.nom_fichier}"'
    return response


@login_required
def compter_non_lus(request):
    """API AJAX : nombre total de messages non lus pour le badge de notification."""
    user = request.user
    total = 0
    for conv in _get_conversations(user):
        total += conv.non_lus_pour(user)
    return JsonResponse({'non_lus': total})


@login_required
@require_POST
def archiver_conversation(request, uuid):
    user = request.user
    conv = get_object_or_404(Conversation, uuid=uuid)
    if not conv.is_participant(user):
        raise Http404
    if conv.participant_1_id == user.pk:
        conv.archivee_p1 = True
    else:
        conv.archivee_p2 = True
    conv.save(update_fields=['archivee_p1', 'archivee_p2'])
    journaliser(user, 'conversation_archivee', 'Conversation', conv.uuid, request=request)
    return redirect('messagerie:liste_conversations')
