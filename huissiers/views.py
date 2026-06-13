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
    significations = Signification.objects.filter(huissier=huissier).select_related('justiciable')
    stats = {
        'envoyees': significations.count(),
        'en_attente': significations.filter(statut__in=['en_attente', 'relance_1', 'relance_2']).count(),
        'acceptees': significations.filter(statut__in=['acceptee', 'repondu']).count(),
        'reponses_non_vues': significations.filter(statut='repondu', reponse__vue_par_huissier=False).count(),
    }
    recentes = significations.order_by('-date_envoi')[:10]
    return render(request, 'huissiers/tableau_de_bord.html', {
        'huissier': huissier, 'stats': stats, 'significations_recentes': recentes
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
    huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                else request.user.profil_clerc.huissier)
    statut = request.GET.get('statut', '')
    periode = request.GET.get('periode', '')
    qs = Signification.objects.filter(huissier=huissier).select_related('justiciable')
    if statut:
        qs = qs.filter(statut=statut)
    if periode:
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now()
        if periode == 'mois':
            qs = qs.filter(date_envoi__gte=today - timedelta(days=30))
        elif periode == '3mois':
            qs = qs.filter(date_envoi__gte=today - timedelta(days=90))
    return render(request, 'huissiers/liste_significations.html', {
        'significations': qs.order_by('-date_envoi'),
        'statut_filtre': statut, 'periode': periode,
        'STATUTS': Signification.STATUT_CHOICES,
    })


@login_required
@huissier_required
def inviter_justiciable(request):
    if request.method == 'POST':
        email = escape(request.POST.get('email', '').strip().lower())
        if not email:
            from django.contrib import messages
            messages.error(request, "L'email est requis.")
            return redirect(request.path)
        huissier = (request.user.profil_huissier if request.user.role == User.HUISSIER
                    else request.user.profil_clerc.huissier)
        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        from notifications.service import envoyer_invitation_justiciable
        from justiciables.models import InvitationJusticiable
        from django.utils import timezone
        from datetime import timedelta
        token_brut, token_hache = creer_token_activation(
            email, TokenActivation.INVITATION_JUSTICIABLE,
            {'huissier_uuid': str(huissier.uuid)}, heures=72
        )
        InvitationJusticiable.objects.create(
            huissier=huissier,
            email_cible=email,
            token=token_hache,
            date_expiration=timezone.now() + timedelta(hours=72),
        )
        envoyer_invitation_justiciable(email, huissier, token_brut)
        from securite.audit import journaliser
        journaliser(request.user, 'invitation_justiciable_envoyee', 'InvitationJusticiable', '', request=request)
        from django.contrib import messages
        messages.success(request, f"Invitation envoyée à {email}.")
        return redirect('huissiers:tableau_de_bord')
    return render(request, 'huissiers/inviter_justiciable.html')
