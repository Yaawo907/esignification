from cryptography.fernet import Fernet
from django.conf import settings
import hashlib


def get_fernet():
    return Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)


def chiffrer_fichier(data: bytes) -> bytes:
    return get_fernet().encrypt(data)


def dechiffrer_fichier(data: bytes) -> bytes:
    return get_fernet().decrypt(data)


def hash_fichier(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chiffrer_texte(texte: str) -> str:
    return get_fernet().encrypt(texte.encode()).decode()


def dechiffrer_texte(texte_chiffre: str) -> str:
    return get_fernet().decrypt(texte_chiffre.encode()).decode()
