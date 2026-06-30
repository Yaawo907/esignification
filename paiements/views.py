import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.models import User
from paiements.models import CommandeCredit
from paiements.services.callback_urls import get_callback_url_kkiapay
from paiements.services.credits import (
    creer_commande_credit,
    get_solde,
    prix_credit_fcfa,
)
from paiements.services.kkiapay import (
    construire_state_achat,
    kkiapay_configure,
    kkiapay_public_key_affichage,
)
from paiements.services.traitement_paiement import traiter_paiement_kkiapay_credits
from securite.audit import journaliser

logger = logging.getLogger(__name__)


def _huissier_utilisateur(user):
    if user.role == User.HUISSIER:
        return user.profil_huissier
    if user.role == User.CLERC:
        return user.profil_clerc.huissier
    return None


def _require_huissier(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'/connexion/?next={request.path}')
        if request.user.role not in (User.HUISSIER, User.CLERC):
            return redirect('/')
        return view_func(request, *args, **kwargs)
    return wrapped


def _finaliser_session_commande(request, commande):
    if commande and 'commande_credit_uuid' in request.session:
        if str(request.session.get('commande_credit_uuid')) == str(commande.uuid):
            del request.session['commande_credit_uuid']


@login_required
@_require_huissier
def achat_credits(request):
    huissier = _huissier_utilisateur(request.user)
    config = __import__('administration.models', fromlist=['ConfigurationPlateforme']).ConfigurationPlateforme.get()

    # Fallback mercure-h : callback Kkiapay raté mais transaction_id dans l'URL
    transaction_id = request.GET.get('transaction_id')
    if transaction_id:
        state_query = request.GET.get('state') or request.GET.get('data') or ''
        resultat = traiter_paiement_kkiapay_credits(transaction_id, state_query)
        if resultat.success:
            if resultat.deja_traite:
                messages.info(request, resultat.message)
            else:
                journaliser(
                    request.user,
                    'achat_credits_kkiapay',
                    'CommandeCredit', resultat.commande.uuid,
                    description=f'{resultat.commande.nb_credits} crédit(s)',
                    request=request,
                )
                messages.success(request, resultat.message)
                _finaliser_session_commande(request, resultat.commande)
        else:
            messages.error(request, resultat.message)
        return redirect('paiements:achat_credits')

    solde = get_solde(huissier)
    mouvements = huissier.mouvements_credits.select_related(
        'signification', 'signification__justiciable',
    ).all()[:20]
    commandes = huissier.commandes_credits.all()[:10]

    if request.method == 'POST':
        action = request.POST.get('action', '')
        if action == 'preparer_achat':
            try:
                nb = Decimal(request.POST.get('nb_credits', '0').replace(',', '.'))
            except InvalidOperation:
                messages.error(request, 'Nombre de crédits invalide.')
                return redirect(request.path)
            if not kkiapay_configure():
                messages.error(request, "Le paiement en ligne n'est pas encore configuré par l'administrateur.")
                return redirect(request.path)
            try:
                commande = creer_commande_credit(huissier, nb)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(request.path)
            request.session['commande_credit_uuid'] = str(commande.uuid)
            return redirect('paiements:achat_credits')

    commande_en_cours = None
    commande_uuid = request.session.get('commande_credit_uuid')
    if commande_uuid:
        commande_en_cours = CommandeCredit.objects.filter(
            uuid=commande_uuid, huissier=huissier, statut=CommandeCredit.STATUT_EN_ATTENTE,
        ).first()

    callback_url = get_callback_url_kkiapay(request)
    cancel_url = request.build_absolute_uri(reverse('paiements:achat_credits'))

    return render(request, 'huissiers/achat_credits.html', {
        'huissier': huissier,
        'solde': solde,
        'prix_credit': prix_credit_fcfa(),
        'mouvements': mouvements,
        'commandes': commandes,
        'kkiapay_actif': kkiapay_configure(),
        'kkiapay_sandbox': config.kkiapay_sandbox,
        'kkiapay_public_key': kkiapay_public_key_affichage(),
        'commande_en_cours': commande_en_cours,
        'callback_url': callback_url,
        'cancel_url': cancel_url,
    })


@require_http_methods(['GET', 'POST'])
def callback_kkiapay(request):
    transaction_id = request.GET.get('transaction_id') or request.POST.get('transaction_id')
    if not transaction_id:
        messages.error(request, 'Transaction Kkiapay introuvable.')
        return redirect('paiements:achat_credits')

    state_query = request.GET.get('state') or request.GET.get('data') or ''
    resultat = traiter_paiement_kkiapay_credits(transaction_id, state_query)

    if resultat.success:
        if resultat.deja_traite:
            messages.info(request, resultat.message)
        else:
            journaliser(
                request.user if request.user.is_authenticated else None,
                'achat_credits_kkiapay',
                'CommandeCredit', resultat.commande.uuid,
                description=f'{resultat.commande.nb_credits} crédit(s)',
                request=request,
            )
            messages.success(request, resultat.message)
            _finaliser_session_commande(request, resultat.commande)
        return redirect('paiements:achat_credits')

    # API indisponible : laisser achat_credits tenter le fallback avec le state client
    if state_query and state_query.startswith('esignif_credit_'):
        messages.info(request, 'Paiement reçu. Finalisation en cours…')
        params = urlencode({'transaction_id': transaction_id, 'state': state_query})
        return redirect(f"{reverse('paiements:achat_credits')}?{params}")

    messages.error(request, resultat.message)
    return redirect('paiements:achat_credits')


@login_required
@_require_huissier
@require_http_methods(['POST'])
def api_preparer_paiement(request):
    """Prépare une commande et retourne les données widget Kkiapay (AJAX)."""
    if not kkiapay_configure():
        return JsonResponse({'success': False, 'error': 'Paiement non configuré.'}, status=400)
    huissier = _huissier_utilisateur(request.user)
    try:
        body = json.loads(request.body or '{}')
        nb = Decimal(str(body.get('nb_credits', '0')).replace(',', '.'))
    except (json.JSONDecodeError, InvalidOperation):
        return JsonResponse({'success': False, 'error': 'Nombre de crédits invalide.'}, status=400)
    try:
        commande = creer_commande_credit(huissier, nb)
    except ValueError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    state = construire_state_achat(commande.uuid, commande.montant_fcfa)
    config = __import__('administration.models', fromlist=['ConfigurationPlateforme']).ConfigurationPlateforme.get()
    return JsonResponse({
        'success': True,
        'commande_uuid': str(commande.uuid),
        'montant': commande.montant_fcfa,
        'nb_credits': str(commande.nb_credits),
        'state': state,
        'callback_url': get_callback_url_kkiapay(request),
        'cancel_url': request.build_absolute_uri(reverse('paiements:achat_credits')),
        'public_key': kkiapay_public_key_affichage(),
        'sandbox': config.kkiapay_sandbox,
    })


@login_required
@_require_huissier
@require_http_methods(['POST'])
def verifier_paiement_ajax(request):
    """Vérification manuelle d'une transaction Kkiapay (souci technique callback)."""
    transaction_id = (request.POST.get('transaction_id') or '').strip()
    commande_uuid = (request.POST.get('commande_uuid') or '').strip()
    if not transaction_id:
        return JsonResponse({'success': False, 'error': 'Identifiant de transaction requis.'}, status=400)

    huissier = _huissier_utilisateur(request.user)
    state_query = ''
    if commande_uuid:
        commande = CommandeCredit.objects.filter(uuid=commande_uuid, huissier=huissier).first()
        if not commande:
            return JsonResponse({'success': False, 'error': 'Commande introuvable.'}, status=404)
        state_query = commande.reference_client or construire_state_achat(
            commande.uuid, commande.montant_fcfa,
        )

    resultat = traiter_paiement_kkiapay_credits(transaction_id, state_query)
    if not resultat.success:
        return JsonResponse({
            'success': False,
            'error': resultat.message,
            'provider_status': resultat.provider_status,
        }, status=400)

    if resultat.commande and resultat.commande.huissier_id != huissier.pk:
        return JsonResponse({'success': False, 'error': 'Cette transaction ne concerne pas votre étude.'}, status=403)

    if not resultat.deja_traite:
        journaliser(
            request.user,
            'achat_credits_kkiapay_manuel',
            'CommandeCredit', resultat.commande.uuid,
            description=f'{resultat.commande.nb_credits} crédit(s) — vérif. manuelle',
            request=request,
        )
        _finaliser_session_commande(request, resultat.commande)

    return JsonResponse({
        'success': True,
        'message': resultat.message,
        'deja_traite': resultat.deja_traite,
        'commande_uuid': str(resultat.commande.uuid),
        'statut': resultat.commande.statut,
        'statut_label': resultat.commande.get_statut_display(),
        'provider_status': resultat.provider_status,
        'nb_credits': str(resultat.commande.nb_credits),
        'solde': str(get_solde(huissier)),
    })
