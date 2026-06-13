import secrets
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.conf import settings


def generer_token(longueur: int = 64) -> str:
    return secrets.token_urlsafe(longueur)


def hasher_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def creer_token_activation(email: str, type_token: str, metadata: dict = None, heures: int = None) -> tuple:
    from accounts.models import TokenActivation
    if heures is None:
        heures = settings.ACTIVATION_TOKEN_EXPIRY_HOURS
    token_brut = generer_token()
    token_hache = hasher_token(token_brut)
    expiry = timezone.now() + timedelta(hours=heures)
    TokenActivation.objects.create(
        token=token_hache,
        type_token=type_token,
        email=email,
        date_expiration=expiry,
        metadata=metadata or {},
    )
    return token_brut, token_hache


def valider_token(token_brut: str, type_token: str):
    from accounts.models import TokenActivation
    token_hache = hasher_token(token_brut)
    try:
        obj = TokenActivation.objects.get(token=token_hache, type_token=type_token)
        if not obj.est_valide:
            return None, "Token expiré ou déjà utilisé"
        return obj, None
    except TokenActivation.DoesNotExist:
        return None, "Token invalide"


def marquer_token_utilise(token_obj) -> None:
    token_obj.utilise = True
    token_obj.save(update_fields=['utilise'])
