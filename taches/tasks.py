from django.utils import timezone
from datetime import timedelta
import logging
logger = logging.getLogger(__name__)


def relancer_significations():
    """Vérifie et envoie les relances automatiques"""
    from significations.models import Signification, RelanceSignification
    from administration.models import ConfigurationPlateforme
    from notifications.service import envoyer_email
    config = ConfigurationPlateforme.get()
    now = timezone.now()
    # Relance 1
    seuil_r1 = now - timedelta(days=config.delai_relance_1_jours)
    sigs_r1 = Signification.objects.filter(
        statut=Signification.STATUT_EN_ATTENTE,
        date_envoi__lte=seuil_r1
    ).exclude(relances__numero_relance=1)
    for sig in sigs_r1:
        RelanceSignification.objects.create(signification=sig, numero_relance=1)
        sig.statut = Signification.STATUT_RELANCE_1
        sig.save(update_fields=['statut'])
        corps = f"<p>Rappel : la signification <strong>{sig.reference}</strong> est en attente de votre réponse.</p>"
        envoyer_email(sig.justiciable.email_domicile, f"Rappel — {sig.reference}", corps)
        logger.info(f"Relance 1 envoyée : {sig.reference}")
    # Relance 2
    seuil_r2 = now - timedelta(days=config.delai_relance_2_jours)
    sigs_r2 = Signification.objects.filter(
        statut=Signification.STATUT_RELANCE_1,
        date_envoi__lte=seuil_r2
    ).exclude(relances__numero_relance=2)
    for sig in sigs_r2:
        RelanceSignification.objects.create(signification=sig, numero_relance=2)
        sig.statut = Signification.STATUT_RELANCE_2
        sig.save(update_fields=['statut'])
        _generer_constat_non_reception(sig)
        corps = f"<p>Dernier rappel : la signification <strong>{sig.reference}</strong> est toujours en attente.</p>"
        envoyer_email(sig.justiciable.email_domicile, f"Dernier rappel — {sig.reference}", corps)
        logger.info(f"Relance 2 envoyée : {sig.reference}")


def _generer_constat_non_reception(sig):
    from securite.chiffrement import chiffrer_fichier
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    import io
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, h-60, w, 60, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h-38, f"{config.nom_plateforme} — Constat de non-réception")
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica", 11)
    y = h - 100
    c.drawString(40, y, f"Signification : {sig.reference}")
    y -= 25
    c.drawString(40, y, f"Huissier : Me {sig.huissier.prenom} {sig.huissier.nom}")
    y -= 25
    c.drawString(40, y, f"Justiciable : {sig.justiciable.nom_complet}")
    y -= 25
    c.drawString(40, y, f"Email domicile : {sig.justiciable.email_domicile}")
    y -= 25
    c.drawString(40, y, f"Date d'envoi : {sig.date_envoi.strftime('%d/%m/%Y %H:%M:%S')}")
    y -= 25
    c.drawString(40, y, f"Date constat : {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}")
    y -= 40
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(40, y, "Aucune réponse n'a été reçue malgré les relances effectuées.")
    c.showPage()
    c.save()
    pdf_data = buffer.getvalue()
    from significations.models import RelanceSignification
    relance = RelanceSignification.objects.get(signification=sig, numero_relance=2)
    relance.constat_chiffre = chiffrer_fichier(pdf_data)
    relance.save(update_fields=['constat_chiffre'])


def executer_lot_merkle():
    """Lot Merkle quotidien — horodatage Certigna (certificats + réponses)."""
    from administration.models import ConfigurationPlateforme, LotMerkle
    from significations.models import CertificatSignification, ReponseJusticiable
    from securite.merkle import construire_arbre_merkle, chemin_preuve

    config = ConfigurationPlateforme.get()
    today = timezone.now().date()
    if LotMerkle.objects.filter(date_lot=today).exists():
        logger.info(f"Lot Merkle {today} déjà traité.")
        return

    certs = list(CertificatSignification.objects.filter(
        date_generation__date=today, lot_merkle__isnull=True,
    ))
    reponses = list(ReponseJusticiable.objects.filter(
        date_envoi_justiciable__date=today,
        lot_merkle__isnull=True,
    ).exclude(hash_reponse=''))

    items = [(c.hash_certificat, c) for c in certs] + [(r.hash_reponse, r) for r in reponses]
    if not items:
        logger.info("Aucun certificat ni réponse à horodater aujourd'hui.")
        return

    feuilles = [h for h, _ in items]
    hash_racine, _ = construire_arbre_merkle(feuilles)
    statut = 'local'
    jeton = None
    if config.certigna_active and config.certigna_tsa_url and config.certigna_login:
        jeton = _horodater_certigna(hash_racine, config)
        if jeton:
            statut = 'certifie'
            config.certigna_jetons_restants = max(0, config.certigna_jetons_restants - 1)
            config.save(update_fields=['certigna_jetons_restants'])

    lot = LotMerkle.objects.create(
        date_lot=today,
        hash_racine=hash_racine,
        jeton_certigna=jeton,
        nb_actes_couverts=len(items),
        statut=statut,
    )

    for idx, (_, obj) in enumerate(items):
        preuve = chemin_preuve(feuilles, idx)
        obj.lot_merkle = lot
        obj.hash_merkle = hash_racine
        obj.chemin_merkle = preuve
        update_fields = ['lot_merkle', 'hash_merkle', 'chemin_merkle']
        if jeton and hasattr(obj, 'horodatage_certigna'):
            obj.horodatage_certigna = jeton
            update_fields.append('horodatage_certigna')
        obj.save(update_fields=update_fields)

    logger.info(
        f"Lot Merkle {today} : {len(certs)} cert(s), {len(reponses)} réponse(s), statut={statut}",
    )
    # Alerte si jetons bas
    if config.certigna_active and config.certigna_jetons_restants <= config.certigna_seuil_alerte_jetons:
        from notifications.service import envoyer_email
        corps = f"<p>Attention : il ne reste que <strong>{config.certigna_jetons_restants} jetons</strong> Certigna. Veuillez recharger votre compte.</p>"
        if config.email_contact:
            envoyer_email(config.email_contact, "Alerte jetons Certigna", corps)


def _horodater_certigna(hash_racine: str, config) -> bytes:
    """Envoie une requête TSA à Certigna et retourne le jeton"""
    try:
        import struct, hashlib, base64, urllib.request, urllib.error
        from securite.chiffrement import dechiffrer_texte
        # Construire la requête TSA (RFC 3161 simplifié)
        hash_bytes = bytes.fromhex(hash_racine)
        # TimeStampReq ASN.1 minimal
        version = b'\x02\x01\x01'
        alg_sha256 = b'\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00'
        hash_val = b'\x04\x20' + hash_bytes
        msg_imprint = b'\x30' + bytes([len(alg_sha256) + len(hash_val)]) + alg_sha256 + hash_val
        nonce = b'\x02\x08' + hash_bytes[:8]
        tsa_req_inner = version + msg_imprint + nonce + b'\x01\x01\xff'
        tsa_req = b'\x30' + bytes([len(tsa_req_inner)]) + tsa_req_inner
        password = dechiffrer_texte(config.certigna_password_chiffre) if config.certigna_password_chiffre else ''
        creds = base64.b64encode(f"{config.certigna_login}:{password}".encode()).decode()
        req = urllib.request.Request(
            config.certigna_tsa_url,
            data=tsa_req,
            headers={'Content-Type': 'application/timestamp-query', 'Authorization': f'Basic {creds}'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read()
    except Exception as e:
        logger.error(f"Erreur horodatage Certigna : {e}")
        return None


def nettoyer_tokens_expires():
    """Supprime les tokens expirés"""
    from accounts.models import TokenActivation
    from django.utils import timezone
    deleted, _ = TokenActivation.objects.filter(date_expiration__lt=timezone.now(), utilise=True).delete()
    logger.info(f"Tokens nettoyés : {deleted}")


def synchroniser_signatures_yousign():
    """Rattrapage automatique si un webhook Yousign n'a pas été reçu."""
    from significations.models import Signification
    from significations.views import synchroniser_signification_yousign

    qs = Signification.objects.filter(
        statut=Signification.STATUT_ATTENTE_SIGNATURE,
    ).exclude(yousign_signature_request_id='')

    for sig in qs:
        try:
            ok, message = synchroniser_signification_yousign(sig)
            if ok:
                logger.info("Yousign sync %s : %s", sig.reference, message)
            else:
                logger.debug("Yousign sync %s : %s", sig.reference, message)
        except Exception as exc:
            logger.error("Yousign sync %s : %s", sig.reference, exc)
