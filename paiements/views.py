import json
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import escape
from django.views.decorators.http import require_http_methods

from accounts.models import User
from huissiers.models import ProfilHuissier
from paiements.models import CommandeCredit
from paiements.services.credits import (
    creer_commande_credit,
    finaliser_achat_credits,
    get_solde,
    prix_credit_fcfa,
)
from paiements.services.kkiapay import (
    KKiaPayService,
    construire_state_achat,
    kkiapay_configure,
    kkiapay_public_key_affichage,
)
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


@login_required
@_require_huissier
def achat_credits(request):
    huissier = _huissier_utilisateur(request.user)
    config = __import__('administration.models', fromlist=['ConfigurationPlateforme']).ConfigurationPlateforme.get()
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
                messages.error(request, "Nombre de crédits invalide.")
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

    callback_url = request.build_absolute_uri(reverse('paiements:callback_kkiapay'))
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


@require_http_methods(["GET", "POST"])
def callback_kkiapay(request):
    transaction_id = request.GET.get('transaction_id') or request.POST.get('transaction_id')
    if not transaction_id:
        messages.error(request, "Transaction Kkiapay introuvable.")
        return redirect('paiements:achat_credits')

    if CommandeCredit.objects.filter(
        transaction_kkiapay=transaction_id, statut=CommandeCredit.STATUT_COMPLETE,
    ).exists():
        messages.info(request, "Ce paiement a déjà été enregistré.")
        return redirect('paiements:achat_credits')

    service = KKiaPayService()
    result = service.verify_payment(transaction_id)
    if not result.success:
        messages.error(request, f"Paiement non validé : {result.error}")
        return redirect('paiements:achat_credits')

    payment_data = result.data
    status = (payment_data.get('status') or '').upper()
    if status not in ('SUCCESS', 'COMPLETED', 'SUCCESSFUL'):
        messages.error(request, "Le paiement n'a pas abouti.")
        return redirect('paiements:achat_credits')

    metadata = payment_data.get('metadata', {})
    commande_uuid = metadata.get('commande_uuid')
    if not commande_uuid:
        messages.error(request, "Référence de commande introuvable.")
        return redirect('paiements:achat_credits')

    commande = get_object_or_404(CommandeCredit, uuid=commande_uuid)
    montant_paye = int(payment_data.get('amount') or 0)
    if montant_paye and montant_paye != commande.montant_fcfa:
        logger.warning(
            "Montant Kkiapay %s ≠ attendu %s pour commande %s",
            montant_paye, commande.montant_fcfa, commande.uuid,
        )

    finaliser_achat_credits(commande, transaction_id)
    journaliser(
        request.user if request.user.is_authenticated else None,
        'achat_credits_kkiapay',
        'CommandeCredit', commande.uuid,
        description=f"{commande.nb_credits} crédit(s)",
        request=request,
    )
    if 'commande_credit_uuid' in request.session:
        del request.session['commande_credit_uuid']
    messages.success(request, f"{commande.nb_credits} crédit(s) ajouté(s) à votre solde.")
    return redirect('paiements:achat_credits')


@login_required
@_require_huissier
@require_http_methods(["POST"])
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
    return JsonResponse({
        'success': True,
        'commande_uuid': str(commande.uuid),
        'montant': commande.montant_fcfa,
        'nb_credits': str(commande.nb_credits),
        'state': state,
        'callback_url': request.build_absolute_uri(reverse('paiements:callback_kkiapay')),
        'cancel_url': request.build_absolute_uri(reverse('paiements:achat_credits')),
        'public_key': kkiapay_public_key_affichage(),
        'sandbox': __import__('administration.models', fromlist=['ConfigurationPlateforme']).ConfigurationPlateforme.get().kkiapay_sandbox,
    })
