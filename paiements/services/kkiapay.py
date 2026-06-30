import logging
from typing import Any, Dict, Optional

import requests

from administration.models import ConfigurationPlateforme
from securite.chiffrement import dechiffrer_texte

from .base import PaymentResponse

logger = logging.getLogger(__name__)


def _config_kkiapay():
    """Retourne (public_key, private_key, secret, sandbox) depuis la config plateforme."""
    config = ConfigurationPlateforme.get()
    public_key = ''
    private_key = ''
    secret = ''
    if config.kkiapay_public_key_chiffre:
        public_key = dechiffrer_texte(config.kkiapay_public_key_chiffre)
    if config.kkiapay_private_key_chiffre:
        private_key = dechiffrer_texte(config.kkiapay_private_key_chiffre)
    if config.kkiapay_secret_chiffre:
        secret = dechiffrer_texte(config.kkiapay_secret_chiffre)
    return public_key, private_key, secret, config.kkiapay_sandbox


def kkiapay_configure() -> bool:
    config = ConfigurationPlateforme.get()
    if not config.kkiapay_active:
        return False
    public_key, private_key, secret, _ = _config_kkiapay()
    return bool(public_key and private_key and secret)


def kkiapay_public_key_affichage() -> str:
    """Clé publique pour le widget (non sensible mais stockée chiffrée)."""
    config = ConfigurationPlateforme.get()
    if not config.kkiapay_public_key_chiffre:
        return ''
    try:
        return dechiffrer_texte(config.kkiapay_public_key_chiffre)
    except Exception:
        return ''


def parser_state_credit(state_data: str) -> Dict[str, Any]:
    """
    Format : esignif_credit_{commande_uuid}_{montant_fcfa}
    """
    metadata: Dict[str, Any] = {}
    prefix = 'esignif_credit_'
    if not state_data or not state_data.startswith(prefix):
        return metadata
    body = state_data[len(prefix):]
    if '_' not in body:
        return metadata
    commande_uuid, montant = body.rsplit('_', 1)
    return {
        'commande_uuid': commande_uuid,
        'expected_amount': montant,
        'widget_data': state_data,
    }


def _format_transaction_response(transaction: dict, transaction_id: str) -> PaymentResponse:
    state = transaction.get('state') or transaction.get('data') or ''
    metadata = parser_state_credit(state)
    formatted = {
        'status': transaction.get('status'),
        'amount': transaction.get('amount'),
        'currency': transaction.get('currency', 'XOF'),
        'transaction_id': transaction_id,
        'metadata': metadata,
        'raw_response': transaction,
    }
    return PaymentResponse(success=True, data=formatted)


class KKiaPayService:
    """Vérification Kkiapay (SDK si disponible, sinon API HTTP)."""

    def __init__(self):
        self.public_key, self.private_key, self.secret, self.sandbox = _config_kkiapay()
        self.base_url = (
            'https://api-sandbox.kkiapay.me' if self.sandbox
            else 'https://api.kkiapay.me'
        )
        self._sdk_client = None
        try:
            from kkiapay import Kkiapay
            self._sdk_client = Kkiapay(
                self.public_key,
                self.private_key,
                self.secret,
                sandbox=self.sandbox,
            )
        except Exception:
            self._sdk_client = None

    def verify_payment(self, transaction_id: str) -> PaymentResponse:
        if self._sdk_client:
            try:
                tx = self._sdk_client.verify_transaction(transaction_id)
                if isinstance(tx, dict):
                    return _format_transaction_response(tx, transaction_id)
                transaction = {
                    'status': getattr(tx, 'status', None),
                    'amount': getattr(tx, 'amount', None),
                    'state': getattr(tx, 'state', None),
                    'currency': 'XOF',
                }
                return _format_transaction_response(transaction, transaction_id)
            except Exception as exc:
                logger.warning('SDK Kkiapay échec tx=%s : %s', transaction_id, exc)

        for api_key in (self.secret, self.private_key, self.public_key):
            if not api_key:
                continue
            result = self._verify_http(transaction_id, api_key)
            if result.success:
                return result
        return PaymentResponse(success=False, error='Vérification Kkiapay impossible.')

    def _verify_http(self, transaction_id: str, api_key: str) -> PaymentResponse:
        headers = {'x-api-key': api_key, 'Content-Type': 'application/json'}
        url = f'{self.base_url}/api/v1/transactions/{transaction_id}'
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                logger.warning(
                    'Kkiapay HTTP %s pour tx %s : %s',
                    response.status_code, transaction_id, response.text[:200],
                )
                return PaymentResponse(
                    success=False,
                    error=f'Erreur API {response.status_code}',
                )
            return _format_transaction_response(response.json(), transaction_id)
        except requests.RequestException as exc:
            logger.exception('Erreur réseau Kkiapay %s', transaction_id)
            return PaymentResponse(success=False, error=str(exc))


def construire_state_achat(commande_uuid, montant_fcfa: int) -> str:
    """Construit le state Kkiapay pour une commande de crédits."""
    return f'esignif_credit_{commande_uuid}_{montant_fcfa}'
