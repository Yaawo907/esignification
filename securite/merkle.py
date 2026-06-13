import hashlib
from typing import List, Tuple


def hash_noeud(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def construire_arbre_merkle(feuilles: List[str]) -> Tuple[str, List[List[str]]]:
    """Construit un arbre de Merkle et retourne (hash_racine, arbre_complet)"""
    if not feuilles:
        return "", []
    if len(feuilles) == 1:
        return feuilles[0], [feuilles]

    niveaux = [feuilles[:]]
    niveau_courant = feuilles[:]

    while len(niveau_courant) > 1:
        nouveau_niveau = []
        for i in range(0, len(niveau_courant), 2):
            gauche = niveau_courant[i]
            droite = niveau_courant[i + 1] if i + 1 < len(niveau_courant) else gauche
            nouveau_niveau.append(hash_noeud(gauche + droite))
        niveaux.append(nouveau_niveau)
        niveau_courant = nouveau_niveau

    return niveau_courant[0], niveaux


def chemin_preuve(feuilles: List[str], index: int) -> List[dict]:
    """Retourne le chemin de preuve pour une feuille donnée"""
    if not feuilles or index >= len(feuilles):
        return []

    chemin = []
    niveau_courant = feuilles[:]
    idx = index

    while len(niveau_courant) > 1:
        if idx % 2 == 0:
            frere_idx = idx + 1 if idx + 1 < len(niveau_courant) else idx
            chemin.append({'position': 'droite', 'hash': niveau_courant[frere_idx]})
        else:
            chemin.append({'position': 'gauche', 'hash': niveau_courant[idx - 1]})

        nouveau_niveau = []
        for i in range(0, len(niveau_courant), 2):
            g = niveau_courant[i]
            d = niveau_courant[i + 1] if i + 1 < len(niveau_courant) else g
            nouveau_niveau.append(hash_noeud(g + d))
        niveau_courant = nouveau_niveau
        idx //= 2

    return chemin


def verifier_preuve(hash_feuille: str, chemin: List[dict], hash_racine: str) -> bool:
    """Vérifie qu'une feuille appartient bien à l'arbre"""
    courant = hash_feuille
    for etape in chemin:
        if etape['position'] == 'droite':
            courant = hash_noeud(courant + etape['hash'])
        else:
            courant = hash_noeud(etape['hash'] + courant)
    return courant == hash_racine
