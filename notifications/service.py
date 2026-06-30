from django.core.mail import send_mail, EmailMultiAlternatives
from django.template import Template, Context
from django.conf import settings
import logging
import threading

logger = logging.getLogger(__name__)


def get_modele_email(type_email: str, langue: str = 'fr'):
    from administration.models import ModeleEmail
    try:
        return ModeleEmail.objects.get(type_email=type_email, langue=langue, actif=True)
    except ModeleEmail.DoesNotExist:
        return None


def _envoyer_email_sync(destinataire: str, sujet: str, corps_html: str, corps_texte: str = '',
                        pieces_jointes=None):
    """Envoi SMTP synchrone — lève l'exception en cas d'échec."""
    msg = EmailMultiAlternatives(
        subject=sujet,
        body=corps_texte or "Veuillez consulter la version HTML.",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinataire],
    )
    msg.attach_alternative(corps_html, "text/html")
    for piece in pieces_jointes or []:
        if len(piece) == 3:
            msg.attach(piece[0], piece[1], piece[2])
    msg.send()
    logger.info(f"Email envoyé avec succès à {destinataire}")


def envoyer_email(destinataire: str, sujet: str, corps_html: str, corps_texte: str = '',
                  pieces_jointes=None):
    """
    Lance l'envoi SMTP dans un thread daemon pour ne pas bloquer
    le worker Gunicorn (évite le SystemExit sur timeout).
    """
    def _thread_target():
        try:
            _envoyer_email_sync(destinataire, sujet, corps_html, corps_texte, pieces_jointes)
        except Exception as e:
            logger.error(f"Erreur envoi email à {destinataire}: {e}")

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return True


def envoyer_activation_huissier(email: str, token_brut: str, langue: str = 'fr', lien: str = None, sync: bool = False):
    from django.conf import settings
    if lien is None:
        lien = f"{settings.SITE_URL.rstrip('/')}/inscription/huissier/?token={token_brut}"
    modele = get_modele_email('activation_huissier', langue)
    ctx = Context({
        'lien_activation': lien,
        'email': email,
        'expiry_heures': settings.ACTIVATION_TOKEN_EXPIRY_HOURS,
    })
    if modele:
        corps = Template(modele.corps_html).render(ctx)
        sujet = Template(modele.sujet).render(ctx)
    else:
        sujet = "Activez votre compte — e-Signification Bénin"
        corps = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;border:1px solid #e5e7eb;border-radius:8px;">
          <div style="background:#1a3c6e;padding:20px 24px;border-radius:6px 6px 0 0;margin:-24px -24px 24px -24px;">
            <h1 style="color:#fff;margin:0;font-size:20px;font-weight:600;">e-Signification Bénin</h1>
          </div>
          <h2 style="color:#1a3c6e;font-size:18px;">Bienvenue sur la plateforme</h2>
          <p style="color:#374151;">Votre compte huissier a été créé par l'administrateur de la plateforme.</p>
          <p style="color:#374151;">Veuillez cliquer sur le bouton ci-dessous pour compléter votre inscription :</p>

          <table width="100%" cellpadding="0" cellspacing="0" style="margin:28px 0;">
            <tr>
              <td align="center">
                <table cellpadding="0" cellspacing="0">
                  <tr>
                    <td style="background:#1a3c6e;border-radius:8px;padding:14px 32px;">
                      <a href="{lien}" style="color:#ffffff;text-decoration:none;font-size:16px;font-weight:600;display:inline-block;">
                        ✉ Activer mon compte
                      </a>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>

          <p style="color:#6b7280;font-size:13px;">
            Si le bouton ne fonctionne pas, copiez ce lien dans votre navigateur :
          </p>
          <p style="word-break:break-all;font-size:12px;">
            <a href="{lien}" style="color:#1a3c6e;">{lien}</a>
          </p>

          <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0;">
          <p style="color:#9ca3af;font-size:12px;margin:0;">
            Ce lien est valable {settings.ACTIVATION_TOKEN_EXPIRY_HOURS} heures.
            Si vous n'attendiez pas cet email, ignorez-le.
          </p>
        </div>"""
    corps_texte = f"""Bienvenue sur e-Signification Bénin

Votre compte huissier a été créé par l'administrateur.
Cliquez sur le lien suivant pour activer votre compte :

{lien}

Ce lien est valable {settings.ACTIVATION_TOKEN_EXPIRY_HOURS} heures.
"""
    if sync:
        _envoyer_email_sync(email, sujet, corps, corps_texte)
        return True
    return envoyer_email(email, sujet, corps, corps_texte)


def envoyer_invitation_justiciable(email_cible: str, huissier, token_brut: str, langue: str = 'fr'):
    from django.conf import settings
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    lien = f"{settings.SITE_URL}/inscription/justiciable/?token={token_brut}"
    sujet = f"Invitation à rejoindre {config.nom_plateforme}"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">{config.nom_plateforme}</h2>
      <p>Madame, Monsieur,</p>
      <p><strong>Me {huissier.prenom} {huissier.nom}</strong>, Huissier de Justice ({huissier.nom_etude}),
      vous contacte dans le cadre de son activité professionnelle.</p>
      <p>Conformément aux dispositions légales en vigueur ({config.article_loi_signification or "relatives à la signification électronique"}),
      l'huissier souhaitrait vous signifier un acte par voie électronique.</p>
      <p>Pour ce faire, vous devez créer votre compte et définir votre <strong>élection de domicile électronique</strong>
      (l'adresse email à laquelle vous souhaitez recevoir les significations).</p>
      <p style="margin:24px 0;">
        <a href="{lien}" style="background:#1a3c6e;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500;">
          Créer mon compte
        </a>
      </p>
      <p style="color:#888;font-size:13px;">Ce lien est valable 72 heures. Si vous ne souhaitez pas recevoir de significations électroniques, ignorez cet email.</p>
    </div>"""
    return envoyer_email(email_cible, sujet, corps)


def envoyer_signification(justiciable, signification, token_accepter: str, token_refuser: str, langue: str = 'fr'):
    from django.conf import settings
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    lien_accepter = f"{settings.SITE_URL}/significations/repondre/{signification.uuid}/?action=accepter&token={token_accepter}"
    lien_refuser = f"{settings.SITE_URL}/significations/repondre/{signification.uuid}/?action=refuser&token={token_refuser}"
    sujet = f"Signification d'acte — {signification.reference} — {config.nom_plateforme}"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">{config.nom_plateforme}</h2>
      <p>Madame, Monsieur <strong>{justiciable.nom_complet}</strong>,</p>
      <p><strong>Me {huissier.prenom} {huissier.nom}</strong>, Huissier de Justice ({huissier.nom_etude}),
      vous adresse la présente signification électronique.</p>
      <p>Référence de l'acte : <strong>{signification.reference}</strong></p>
      {f'<p style="color:#666;font-size:13px;">Base légale : {config.article_loi_signification}</p>' if config.article_loi_signification else ''}
      <p>Veuillez indiquer si vous acceptez ou refusez la réception de cet acte par voie électronique :</p>
      <div style="margin:28px 0;display:flex;gap:16px;">
        <a href="{lien_accepter}" style="background:#0d6e4f;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500;margin-right:12px;">
          ✓ Accepter la signification
        </a>
        <a href="{lien_refuser}" style="background:#a32d2d;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500;">
          ✗ Refuser la signification
        </a>
      </div>
      <p style="color:#888;font-size:12px;">
        En acceptant, vous serez redirigé(e) vers la plateforme pour accéder à votre espace personnel.<br>
        La date et l'heure de réception seront horodatées à la seconde.
      </p>
    </div>"""
    return envoyer_email(justiciable.email_domicile, sujet, corps)


def envoyer_certificat(signification, certificat, langue: str = 'fr'):
    from django.utils import timezone as tz
    from securite.chiffrement import dechiffrer_fichier
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    justiciable = signification.justiciable

    date_rec = certificat.date_reception
    if tz.is_aware(date_rec):
        date_rec = tz.localtime(date_rec)
    date_reception_fmt = date_rec.strftime('%d/%m/%Y à %Hh%Mm%Ss')
    tz_label = certificat.timezone_reception or 'Africa/Porto-Novo'

    sujet = f"Certificat de signification — {signification.reference}"
    nom_pdf = f"certificat_{signification.reference}.pdf"
    pieces_jointes = []
    if certificat.fichier_certificat_chiffre:
        try:
            pdf_data = dechiffrer_fichier(bytes(certificat.fichier_certificat_chiffre))
            pieces_jointes = [(nom_pdf, pdf_data, 'application/pdf')]
        except Exception as e:
            logger.error(f"Impossible de joindre le PDF certificat {signification.reference}: {e}")

    mention_pj = (
        f"<p>Le certificat officiel est joint à cet email au format <strong>PDF</strong> "
        f"(<em>{nom_pdf}</em>) — document imprimable.</p>"
        if pieces_jointes else
        "<p>Le certificat PDF n'a pas pu être joint ; consultez votre espace sur la plateforme.</p>"
    )
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">Certificat de signification électronique</h2>
      <p>Référence : <strong>{signification.reference}</strong></p>
      <p>Acte réceptionné par : <strong>{justiciable.nom_complet}</strong></p>
      <p>Date et heure de réception : <strong>{date_reception_fmt}</strong> (heure de {tz_label})</p>
      <p>Ce certificat atteste que l'acte a été remis électroniquement à la date et heure indiquées.</p>
      {mention_pj}
      <p style="color:#888;font-size:12px;">Vous pouvez également consulter et télécharger ce certificat depuis votre espace sur {config.nom_plateforme}.</p>
    </div>"""
    corps_texte = f"""Certificat de signification électronique

Référence : {signification.reference}
Acte réceptionné par : {justiciable.nom_complet}
Date et heure de réception : {date_reception_fmt} (heure de {tz_label})

Ce certificat atteste que l'acte a été remis électroniquement à la date et heure indiquées.
"""
    if pieces_jointes:
        corps_texte += f"\nLe certificat PDF imprimable est joint à cet email ({nom_pdf}).\n"
    corps_texte += f"\nConsultez également votre espace sur {config.nom_plateforme}.\n"

    envoyer_email(huissier.user.email, sujet, corps, corps_texte, pieces_jointes)
    envoyer_email(justiciable.email_domicile, sujet, corps, corps_texte, pieces_jointes)


def envoyer_reponse_huissier(signification, reponse, pdf_data: bytes, langue: str = 'fr'):
    """Notifie l'huissier avec le PDF officiel de réponse en pièce jointe."""
    from django.utils import timezone as tz
    from administration.models import ConfigurationPlateforme

    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    justiciable = signification.justiciable

    date_envoi = reponse.date_envoi_justiciable
    if tz.is_aware(date_envoi):
        date_envoi = tz.localtime(date_envoi)
    date_envoi_fmt = date_envoi.strftime('%d/%m/%Y à %Hh%Mm%Ss')

    sujet = f"Réponse reçue — {signification.reference}"
    nom_pdf = reponse.nom_fichier_reponse or f"reponse_{signification.reference}.pdf"
    pieces_jointes = [(nom_pdf, pdf_data, 'application/pdf')] if pdf_data else []

    mention_annexe = ''
    if reponse.nom_fichier_annexe:
        mention_annexe = (
            f"<p>Une pièce jointe (<em>{reponse.nom_fichier_annexe}</em>) "
            f"a été fusionnée au document officiel.</p>"
        )

    mention_pj = (
        f"<p>Le document officiel de réponse est joint à cet email au format <strong>PDF</strong> "
        f"(<em>{nom_pdf}</em>) — imprimable pour production devant juridiction.</p>"
        if pieces_jointes else
        "<p>Connectez-vous à la plateforme pour consulter la réponse.</p>"
    )

    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">Réponse du justiciable</h2>
      <p>Le justiciable <strong>{justiciable.nom_complet}</strong> a transmis une réponse
      pour la signification <strong>{signification.reference}</strong>.</p>
      <p>Date et heure d'envoi : <strong>{date_envoi_fmt}</strong></p>
      {mention_annexe}
      {mention_pj}
      <p style="color:#888;font-size:12px;">Consultez également la réponse depuis votre espace sur {config.nom_plateforme}.</p>
    </div>"""

    corps_texte = f"""Réponse du justiciable

Justiciable : {justiciable.nom_complet}
Signification : {signification.reference}
Date d'envoi : {date_envoi_fmt}
"""
    if reponse.nom_fichier_annexe:
        corps_texte += f"Annexe fusionnée : {reponse.nom_fichier_annexe}\n"
    if pieces_jointes:
        corps_texte += f"\nLe PDF officiel est joint ({nom_pdf}).\n"
    corps_texte += f"\nConsultez votre espace sur {config.nom_plateforme}.\n"

    return envoyer_email(huissier.user.email, sujet, corps, corps_texte, pieces_jointes)


def envoyer_recuperation_mdp(email: str, token_brut: str, langue: str = 'fr'):
    from django.conf import settings
    lien = f"{settings.SITE_URL}/reinitialiser-mdp/?token={token_brut}"
    sujet = "Réinitialisation de votre mot de passe — e-Signification Bénin"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">Réinitialisation de mot de passe</h2>
      <p>Une demande de réinitialisation de mot de passe a été effectuée pour votre compte.</p>
      <p style="margin:24px 0;">
        <a href="{lien}" style="background:#1a3c6e;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;">
          Réinitialiser mon mot de passe
        </a>
      </p>
      <p style="color:#888;font-size:13px;">Ce lien est valable 2 heures. Si vous n'avez pas fait cette demande, ignorez cet email.</p>
    </div>"""
    return envoyer_email(email, sujet, corps)


def envoyer_preuve_yousign_huissier(signification, pdf_signe=None, audit_trail_pdf=None):
    """
    Envoie à l'huissier la preuve de signature Yousign (audit trail + acte signé).
    Appelé après signature_request.done (webhook ou sync).
    """
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    justiciable = signification.justiciable

    nom_acte = f"acte_signe_{signification.reference}.pdf"
    nom_preuve = f"preuve_yousign_{signification.reference}.pdf"
    pieces_jointes = []

    if pdf_signe:
        pieces_jointes.append((nom_acte, pdf_signe, 'application/pdf'))
    elif signification.fichier_chiffre:
        try:
            from securite.chiffrement import dechiffrer_fichier
            pieces_jointes.append((
                nom_acte,
                dechiffrer_fichier(bytes(signification.fichier_chiffre)),
                'application/pdf',
            ))
        except Exception as e:
            logger.error("Preuve Yousign : acte signé non joint pour %s — %s",
                         signification.reference, e)

    if audit_trail_pdf:
        pieces_jointes.append((nom_preuve, audit_trail_pdf, 'application/pdf'))
    elif signification.yousign_audit_trail_chiffre:
        try:
            from securite.chiffrement import dechiffrer_fichier
            pieces_jointes.append((
                nom_preuve,
                dechiffrer_fichier(bytes(signification.yousign_audit_trail_chiffre)),
                'application/pdf',
            ))
        except Exception as e:
            logger.error("Preuve Yousign : audit trail non joint pour %s — %s",
                         signification.reference, e)

    mention_pj = ''
    if any(p[0] == nom_preuve for p in pieces_jointes):
        mention_pj = (
            f"<p>Le <strong>dossier de preuve Yousign</strong> (audit trail) est joint "
            f"à cet email (<em>{nom_preuve}</em>). Il atteste l'authenticité de votre "
            f"signature électronique (horodatage, OTP SMS, certificat).</p>"
        )
    if any(p[0] == nom_acte for p in pieces_jointes):
        mention_pj += (
            f"<p>L'<strong>acte signé</strong> est également joint (<em>{nom_acte}</em>).</p>"
        )
    if not mention_pj:
        mention_pj = (
            "<p>Consultez votre espace huissier pour télécharger l'acte signé "
            "et le dossier de preuve.</p>"
        )

    sujet = f"Preuve de signature électronique — {signification.reference}"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#0d6e4f;">✓ Signature électronique confirmée</h2>
      <p>Maître <strong>{huissier.prenom} {huissier.nom}</strong>,</p>
      <p>Votre signature électronique (Yousign) pour l'acte
      <strong>{signification.reference}</strong> a été enregistrée avec succès.</p>
      <p>L'acte a été transmis au justiciable <strong>{justiciable.nom_complet}</strong>
      ({justiciable.email_domicile}).</p>
      {mention_pj}
      <p style="color:#888;font-size:12px;">
        Conservez le dossier de preuve Yousign — il constitue la trace probatoire
        de votre signature (Signature Électronique Avancée).
      </p>
      <p style="color:#888;font-size:12px;">{config.nom_plateforme}</p>
    </div>"""
    corps_texte = f"""Signature électronique confirmée

Référence : {signification.reference}
Destinataire : {justiciable.nom_complet} ({justiciable.email_domicile})

Votre signature Yousign a été enregistrée. L'acte a été transmis au justiciable.
Consultez les pièces jointes ou votre espace huissier pour le dossier de preuve.
"""
    return envoyer_email(huissier.user.email, sujet, corps, corps_texte, pieces_jointes)


def envoyer_yousign_expiree(signification, raison: str = 'expired'):
    """
    Notifie l'huissier que sa demande de signature Yousign a échoué/expiré.
    L'acte reste en statut attente_signature — l'huissier peut basculer en traditionnel.
    """
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    libelles = {
        'expired': 'a expiré (7 jours sans signature)',
        'canceled': 'a été annulée',
        'rejected': 'a été refusée',
    }
    libelle = libelles.get(raison, 'a échoué')
    sujet = f"⚠ Signature électronique {libelle} — {signification.reference}"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#a32d2d;">Signature électronique — action requise</h2>
      <p>Maître <strong>{huissier.prenom} {huissier.nom}</strong>,</p>
      <p>La demande de signature électronique (Yousign) pour l'acte
      <strong>{signification.reference}</strong> {libelle}.</p>
      <p>L'acte n'a pas encore été transmis au destinataire.</p>
      <p>Veuillez vous connecter à la plateforme pour :</p>
      <ul>
        <li>Basculer cet acte en signification traditionnelle (remise en mains propres), ou</li>
        <li>Contacter l'administrateur pour relancer une demande de signature.</li>
      </ul>
      <p style="color:#888;font-size:12px;">
        Référence : {signification.reference}<br>
        Destinataire : {signification.justiciable.nom_complet}
      </p>
    </div>"""
    return envoyer_email(huissier.user.email, sujet, corps)
