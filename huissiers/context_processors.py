"""Contexte partagé pour l'espace huissier (sidebar, badges)."""


def sidebar_badges_for_huissier(request, huissier):
    from django.db.models import Q
    from justiciables.models import DemandeModificationProfil
    from messagerie.models import Message
    from significations.models import Signification

    nb_demandes_modif = DemandeModificationProfil.objects.filter(
        huissier=huissier, statut='en_attente'
    ).count()
    nb_messages_non_lus = Message.objects.filter(
        Q(conversation__participant_1=request.user) | Q(conversation__participant_2=request.user),
        lu=False,
    ).exclude(auteur=request.user).count()
    stats_en_attente = Signification.objects.filter(
        huissier=huissier,
        statut__in=['en_attente', 'relance_1', 'relance_2'],
    ).count()
    return {
        'nb_demandes_modif': nb_demandes_modif,
        'nb_messages_non_lus': nb_messages_non_lus,
        'stats_en_attente': stats_en_attente,
        'solde_credits': _solde_huissier(huissier),
    }


def _solde_huissier(huissier):
    try:
        from paiements.services.credits import get_solde
        return get_solde(huissier)
    except Exception:
        return None


def sidebar_huissier(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    from accounts.models import User
    if request.user.role not in (User.HUISSIER, User.CLERC):
        return {}
    try:
        huissier = (
            request.user.profil_huissier
            if request.user.role == User.HUISSIER
            else request.user.profil_clerc.huissier
        )
    except Exception:
        return {}
    return sidebar_badges_for_huissier(request, huissier)
