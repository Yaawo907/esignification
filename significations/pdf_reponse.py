"""Génération du PDF officiel de réponse du justiciable."""
import base64
import hashlib
import io
import os

from django.utils import timezone as tz_util
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas

PREFIXES_IMAGE_SIGNATURE = (
    'data:image/png;base64,',
    'data:image/jpeg;base64,',
    'data:image/jpg;base64,',
    'data:image/svg+xml;base64,',
    'data:image/webp;base64,',
    'data:image/gif;base64,',
)


def _signature_b64_valide(b64: str) -> bool:
    return bool(b64 and any(b64.startswith(p) for p in PREFIXES_IMAGE_SIGNATURE))


def _image_reader_depuis_b64(b64: str):
    """Convertit une data-URL image en ImageReader ReportLab."""
    from PIL import Image as PilImage

    b64_data = b64.split(',', 1)[1]
    img_bytes = base64.b64decode(b64_data)
    pil_img = PilImage.open(io.BytesIO(img_bytes))
    if pil_img.mode != 'RGBA':
        pil_img = pil_img.convert('RGBA')
    bg = PilImage.new('RGBA', pil_img.size, (255, 255, 255, 255))
    bg.paste(pil_img, mask=pil_img.split()[3])
    sig_buf = io.BytesIO()
    bg.convert('RGB').save(sig_buf, format='PNG')
    sig_buf.seek(0)
    return ImageReader(sig_buf)


def _dessiner_bloc_signature(c, w, y, b64, label, nom_sous_sig, sig_w=180, sig_h=60):
    """Dessine le cadre de signature sur le canvas. Retourne y après le bloc."""
    sig_x = w - 40 - sig_w
    pad = 6
    frame_h = sig_h + pad * 2
    min_y = 130

    if y - frame_h - 30 < min_y:
        c.showPage()
        y = A4[1] - 60

    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(sig_x, y, label)
    y -= 14

    frame_y = y - frame_h
    try:
        sig_img = _image_reader_depuis_b64(b64)
        c.setStrokeColorRGB(0.10, 0.24, 0.43)
        c.setLineWidth(0.8)
        c.rect(sig_x - 4, frame_y, sig_w + 8, frame_h, stroke=1, fill=0)
        c.drawImage(sig_img, sig_x, frame_y + pad, width=sig_w, height=sig_h,
                    preserveAspectRatio=True, mask='auto')
    except Exception:
        c.setStrokeColorRGB(0.10, 0.24, 0.43)
        c.setLineWidth(0.8)
        c.rect(sig_x - 4, frame_y, sig_w + 8, frame_h, stroke=1, fill=0)

    c.setFont("Helvetica-Oblique", 7)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(sig_x + sig_w / 2, frame_y - 10, nom_sous_sig)
    return frame_y - 22


def fusionner_annexe_pdf(pdf_principal: bytes, pdf_annexe: bytes) -> bytes:
    """Fusionne le PDF officiel et une annexe PDF en un seul document."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for data in (pdf_principal, pdf_annexe):
        reader = PdfReader(io.BytesIO(data))
        for page in reader.pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def generer_pdf_reponse(
    signification,
    reponse,
    texte: str,
    annexe_nom: str = '',
    annexe_hash: str = '',
) -> bytes:
    """Génère un PDF imprimable avec les informations de sécurité."""
    from administration.models import ConfigurationPlateforme

    config = ConfigurationPlateforme.get()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    HEADER_H = 100
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, h - HEADER_H, w, HEADER_H, fill=1, stroke=0)

    logo_x = 18
    if config.logo_pays and config.logo_pays.name:
        try:
            chemin_pays = config.logo_pays.path
            if os.path.isfile(chemin_pays):
                img_pays = ImageReader(chemin_pays)
                iw, ih = img_pays.getSize()
                ratio = min(70 / iw, 70 / ih)
                rw, rh = iw * ratio, ih * ratio
                c.drawImage(
                    img_pays, logo_x, h - HEADER_H + (HEADER_H - rh) / 2,
                    width=rw, height=rh, mask='auto', preserveAspectRatio=True,
                )
                logo_x += rw + 10
        except Exception:
            pass

    logo_chambre_w = 0
    if config.logo_chambre and config.logo_chambre.name:
        try:
            chemin_chambre = config.logo_chambre.path
            if os.path.isfile(chemin_chambre):
                img_chambre = ImageReader(chemin_chambre)
                iw, ih = img_chambre.getSize()
                ratio = min(70 / iw, 70 / ih)
                rw, rh = iw * ratio, ih * ratio
                logo_chambre_x = w - 18 - rw
                c.drawImage(
                    img_chambre, logo_chambre_x, h - HEADER_H + (HEADER_H - rh) / 2,
                    width=rw, height=rh, mask='auto', preserveAspectRatio=True,
                )
                logo_chambre_w = rw + 10
        except Exception:
            pass

    texte_x_debut = logo_x + 6
    texte_largeur = (w - logo_chambre_w - 18) - texte_x_debut
    texte_centre = texte_x_debut + texte_largeur / 2
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(texte_centre, h - 40, config.nom_plateforme)
    c.setFont("Helvetica", 10)
    c.drawCentredString(texte_centre, h - 58, "REPONSE DU JUSTICIABLE")
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(texte_centre, h - 73, f"Republique du {config.pays}")

    c.setStrokeColorRGB(0.10, 0.24, 0.43)
    c.setLineWidth(1.5)
    c.line(40, h - HEADER_H - 18, w - 40, h - HEADER_H - 18)

    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(w / 2, h - HEADER_H - 40, "REPONSE OFFICIELLE DU JUSTICIABLE")

    justiciable = signification.justiciable
    huissier = signification.huissier
    date_envoi = reponse.date_envoi_justiciable
    if tz_util.is_aware(date_envoi):
        date_envoi = tz_util.localtime(date_envoi)
    date_envoi_fmt = date_envoi.strftime('%d/%m/%Y à %Hh%Mm%Ss')
    tz_label = str(tz_util.get_current_timezone())

    y = h - HEADER_H - 68
    c.setFont("Helvetica", 10)
    infos = [
        ("Reference signification", signification.reference),
        ("Huissier", f"Me {huissier.prenom} {huissier.nom}"),
        ("Etude", huissier.nom_etude),
        ("Justiciable", justiciable.nom_complet),
        ("Email domicile", justiciable.email_domicile),
    ]
    if justiciable.npi:
        infos.append(("NPI", justiciable.npi))
    if justiciable.ifu:
        infos.append(("IFU", justiciable.ifu))
    infos.extend([
        ("Date et heure d'envoi", f"{date_envoi_fmt} ({tz_label})"),
        ("Reference reponse", str(reponse.uuid)),
    ])
    if annexe_nom:
        infos.append(("Annexe jointe", annexe_nom[:80]))
    if annexe_hash:
        infos.append(("Hash annexe (SHA-256)", annexe_hash[:48] + "..."))

    for i, (label, valeur) in enumerate(infos):
        if i % 2 == 0:
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(36, y - 5, w - 72, 20, fill=1, stroke=0)
        c.setFillColorRGB(0.10, 0.24, 0.43)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(42, y + 3, f"{label} :")
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica", 9)
        c.drawString(210, y + 3, str(valeur)[:80])
        y -= 22

    y -= 10
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Contenu de la reponse :")
    y -= 18

    c.setStrokeColorRGB(0.80, 0.85, 0.92)
    c.setLineWidth(0.5)
    corps_haut = y
    corps_bas = 200
    c.rect(36, corps_bas, w - 72, corps_haut - corps_bas, stroke=1, fill=0)

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica", 10)
    texte_affiche = (texte or "").replace('\r\n', '\n').replace('\r', '\n')
    line_height = 14
    max_width = w - 90
    y_texte = corps_haut - 16
    for paragraphe in texte_affiche.split('\n'):
        if not paragraphe.strip():
            y_texte -= line_height
            continue
        for line in simpleSplit(paragraphe, 'Helvetica', 10, max_width):
            if y_texte < corps_bas + 12:
                c.showPage()
                y_texte = h - 60
                c.setFont("Helvetica", 10)
                c.setFillColorRGB(0.1, 0.1, 0.1)
            c.drawString(44, y_texte, line)
            y_texte -= line_height

    y = min(y_texte - 10, corps_bas - 10)

    signature_b64 = getattr(reponse, 'signature_justiciable_b64', '') or ''
    if _signature_b64_valide(signature_b64):
        y = _dessiner_bloc_signature(
            c, w, y, signature_b64,
            label="Signature du justiciable :",
            nom_sous_sig=justiciable.nom_complet[:60],
        )

    if reponse.hash_contenu or signification.hash_acte:
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.5)
        if y < 120:
            c.showPage()
            y = h - 60
        c.line(40, y + 10, w - 40, y + 10)
        y -= 6
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(40, y, "Empreintes de securite :")
        y -= 14
        c.setFont("Helvetica", 7)
        if reponse.hash_contenu:
            c.drawString(40, y, f"Hash contenu (SHA-256) : {reponse.hash_contenu}")
            y -= 12
        if _signature_b64_valide(signature_b64):
            try:
                sig_hash = base64.b64decode(signature_b64.split(',', 1)[1])
                hash_sig = hashlib.sha256(sig_hash).hexdigest()
                c.drawString(40, y, f"Hash signature (SHA-256) : {hash_sig[:48]}...")
                y -= 12
            except Exception:
                pass
        if signification.hash_acte:
            hash_acte = signification.hash_acte
            c.drawString(40, y, f"Hash acte signifie : {hash_acte[:48]}...")
            y -= 12

    if config.article_loi_signification or config.decret_reference:
        y -= 6
        c.setFont("Helvetica-Oblique", 8)
        if config.article_loi_signification:
            c.drawString(40, y, f"Base legale : {config.article_loi_signification[:110]}")
            y -= 14
        if config.decret_reference:
            c.drawString(40, y, f"Decret : {config.decret_reference[:120]}")
            y -= 14

    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(w / 2, 68,
        "Document genere automatiquement par la plateforme e-Signification Benin.")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(w / 2, 57,
        "Reponse transmise par le justiciable identifie, domicile electronique verifie.")
    c.drawCentredString(w / 2, 46,
        "Ce document est imprimable et peut etre produit devant les juridictions.")
    if annexe_nom:
        c.drawCentredString(w / 2, 35,
            "Les pages suivantes contiennent la piece jointe du justiciable.")

    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, 0, w, 35, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 7)
    c.drawString(40, 13, config.copyright_texte or "")
    c.drawRightString(w - 40, 13, f"Genere le {date_envoi_fmt}")

    c.showPage()
    c.save()
    return buffer.getvalue()
