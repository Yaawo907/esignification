"""Validation du placement de signature Yousign (coordonnées PDF)."""

import io

# Limites Yousign API v3 (signature field)
YOUSIGN_SIG_WIDTH_DEFAULT = 120
YOUSIGN_SIG_HEIGHT_DEFAULT = 60
YOUSIGN_SIG_WIDTH_MIN = 85
YOUSIGN_SIG_HEIGHT_MIN = 37
YOUSIGN_SIG_WIDTH_MAX = 2000
YOUSIGN_SIG_HEIGHT_MAX = 1000
YOUSIGN_COORD_MAX = 32767


def extraire_placement_post(post) -> dict:
    """Lit et normalise les champs POST de placement."""
    try:
        page = int(post.get('yousign_sig_page', '').strip())
        x = int(post.get('yousign_sig_x', '').strip())
        y = int(post.get('yousign_sig_y', '').strip())
        width = int(post.get('yousign_sig_width', YOUSIGN_SIG_WIDTH_DEFAULT))
        height = int(post.get('yousign_sig_height', YOUSIGN_SIG_HEIGHT_DEFAULT))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Emplacement de signature invalide. Cliquez sur le PDF pour choisir où signer."
        ) from exc
    return {
        'page': page,
        'x': x,
        'y': y,
        'width': width,
        'height': height,
    }


def valider_placement_yousign(pdf_bytes: bytes, placement: dict) -> dict:
    """
    Vérifie que le placement est dans les limites Yousign et du document PDF.
    Retourne le placement validé.
    """
    from pypdf import PdfReader

    page = placement.get('page')
    x = placement.get('x')
    y = placement.get('y')
    width = placement.get('width', YOUSIGN_SIG_WIDTH_DEFAULT)
    height = placement.get('height', YOUSIGN_SIG_HEIGHT_DEFAULT)

    if page is None or x is None or y is None:
        raise ValueError(
            "Veuillez cliquer sur l'aperçu du PDF pour choisir l'emplacement de votre signature."
        )

    if not isinstance(page, int) or page < 1:
        raise ValueError("Numéro de page de signature invalide.")

    if not isinstance(x, int) or not isinstance(y, int):
        raise ValueError("Coordonnées de signature invalides.")

    if x < 0 or y < 0 or x > YOUSIGN_COORD_MAX or y > YOUSIGN_COORD_MAX:
        raise ValueError("Coordonnées de signature hors limites.")

    if not (YOUSIGN_SIG_WIDTH_MIN <= width <= YOUSIGN_SIG_WIDTH_MAX):
        raise ValueError("Largeur du champ de signature invalide.")

    if not (YOUSIGN_SIG_HEIGHT_MIN <= height <= YOUSIGN_SIG_HEIGHT_MAX):
        raise ValueError("Hauteur du champ de signature invalide.")

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
    except Exception as exc:
        raise ValueError("Impossible de lire le PDF pour valider l'emplacement.") from exc

    if page > num_pages:
        raise ValueError(
            f"La page {page} n'existe pas dans ce document ({num_pages} page"
            f"{'s' if num_pages > 1 else ''})."
        )

    pg = reader.pages[page - 1]
    page_w = float(pg.mediabox.width)
    page_h = float(pg.mediabox.height)

    if x + width > page_w + 1:
        raise ValueError("Le champ de signature dépasse la largeur de la page.")
    if y + height > page_h + 1:
        raise ValueError("Le champ de signature dépasse la hauteur de la page.")

    return {
        'page': page,
        'x': x,
        'y': y,
        'width': width,
        'height': height,
    }
