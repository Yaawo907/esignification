from typing import Any, Dict, Optional


class PaymentResponse:
    """Réponse standardisée des services de paiement."""

    def __init__(self, success: bool, data: Optional[Dict[str, Any]] = None, error: str = ''):
        self.success = success
        self.data = data or {}
        self.error = error

    def to_dict(self):
        return {'success': self.success, 'data': self.data, 'error': self.error}
