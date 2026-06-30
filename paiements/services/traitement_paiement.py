import logging

from paiements.models import CommandeCredit
from paiements.services.credits import finaliser_achat_credits
from paiements.services.kkiapay import KKiaPayService, parser_state_credit

logger = logging.getLogger(__name__)

_STATUTS_OK = frozenset({
    'success', 'completed', 'successful', 'approved', 'paid', 'done', 'succeeded',
})


class ResultatPaiementCredits:
    def __init__(self, success, message='', commande=None, deja_traite=False, provider_status=''):
        self.success = success
        self.message = message
        self.commande = commande
        self.deja_traite = deja_traite
        self.provider_status = provider_status


def _statut_paiement_ok(status) -> bool:
    return (status or '').strip().lower() in _STATUTS_OK


def traiter_paiement_kkiapay_credits(transaction_id: str, state_query: str = '') -> ResultatPaiementCredits:
    """Vérifie et finalise un achat de crédits Kkiapay (callback, fallback ou manuel)."""
    transaction_id = (transaction_id or '').strip()
    if not transaction_id:
        return ResultatPaiementCredits(False, 'Transaction Kkiapay introuvable.')

    existing = CommandeCredit.objects.filter(
        transaction_kkiapay=transaction_id,
        statut=CommandeCredit.STATUT_COMPLETE,
    ).first()
    if existing:
        return ResultatPaiementCredits(
            True, 'Ce paiement a déjà été enregistré.', existing, deja_traite=True,
        )

    service = KKiaPayService()
    result = service.verify_payment(transaction_id)
    payment_data = None

    if result.success:
        payment_data = result.data
    elif state_query and state_query.startswith('esignif_credit_'):
        metadata = parser_state_credit(state_query)
        commande_uuid = metadata.get('commande_uuid')
        if not commande_uuid:
            return ResultatPaiementCredits(False, 'Référence de commande invalide.')
        try:
            commande = CommandeCredit.objects.get(uuid=commande_uuid)
        except CommandeCredit.DoesNotExist:
            return ResultatPaiementCredits(False, 'Commande introuvable.')
        logger.warning(
            'Fallback state Kkiapay tx=%s commande=%s (API: %s)',
            transaction_id, commande_uuid, result.error,
        )
        payment_data = {
            'status': 'approved',
            'amount': commande.montant_fcfa,
            'metadata': metadata,
            'raw_response': {'state': state_query},
        }
    else:
        return ResultatPaiementCredits(
            False,
            f"Paiement non validé : {result.error or 'Vérification Kkiapay impossible.'}",
        )

    provider_status = payment_data.get('status') or ''
    if not _statut_paiement_ok(provider_status):
        return ResultatPaiementCredits(
            False, "Le paiement n'a pas abouti.", provider_status=provider_status,
        )

    metadata = payment_data.get('metadata') or {}
    commande_uuid = metadata.get('commande_uuid')
    if not commande_uuid:
        raw = payment_data.get('raw_response') or {}
        state = raw.get('state') or raw.get('data') or state_query or ''
        metadata = parser_state_credit(state)
        commande_uuid = metadata.get('commande_uuid')

    if not commande_uuid:
        return ResultatPaiementCredits(False, 'Référence de commande introuvable.')

    try:
        commande = CommandeCredit.objects.get(uuid=commande_uuid)
    except CommandeCredit.DoesNotExist:
        return ResultatPaiementCredits(False, 'Commande introuvable.')

    if commande.statut == CommandeCredit.STATUT_COMPLETE:
        return ResultatPaiementCredits(
            True, 'Ce paiement a déjà été enregistré.', commande, deja_traite=True,
        )

    montant_paye = int(payment_data.get('amount') or 0)
    if montant_paye and montant_paye != commande.montant_fcfa:
        logger.warning(
            'Montant Kkiapay %s ≠ attendu %s pour commande %s',
            montant_paye, commande.montant_fcfa, commande.uuid,
        )

    finaliser_achat_credits(commande, transaction_id)
    return ResultatPaiementCredits(
        True,
        f'{commande.nb_credits} crédit(s) ajouté(s) à votre solde.',
        commande,
        provider_status=provider_status,
    )
