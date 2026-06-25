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


def _envoyer_email_sync(destinataire: str, sujet: str, corps_html: str, corps_texte: str = ''):
    """Envoi SMTP synchrone — appelé dans un thread background."""
    try:
        msg = EmailMultiAlternatives(
            subject=sujet,
            body=corps_texte or "Veuillez consulter la version HTML.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[destinataire],
        )
        msg.attach_alternative(corps_html, "text/html")
        msg.send()
        logger.info(f"Email envoyé avec succès à {destinataire}")
    except Exception as e:
        logger.error(f"Erreur envoi email à {destinataire}: {e}")


def envoyer_email(destinataire: str, sujet: str, corps_html: str, corps_texte: str = ''):
    """
    Lance l'envoi SMTP dans un thread daemon pour ne pas bloquer
    le worker Gunicorn (évite le SystemExit sur timeout).
    """
    thread = threading.Thread(
        target=_envoyer_email_sync,
        args=(destinataire, sujet, corps_html, corps_texte),
        daemon=True,
    )
    thread.start()
    return True


def envoyer_activation_huissier(email: str, token_brut: str, langue: str = 'fr'):
    from django.conf import settings
    lien = f"{settings.SITE_URL}/inscription/huissier/?token={token_brut}"
    modele = get_modele_email('activation_huissier', langue)
    if modele:
        t = Template(modele.corps_html)
        corps = t.render(Context({'lien_activation': lien, 'email': email, 'expiry_heures': settings.ACTIVATION_TOKEN_EXPIRY_HOURS}))
        sujet = modele.sujet
    else:
        sujet = "Activez votre compte — e-Signification Bénin"
        corps = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
          <h2 style="color:#1a3c6e;">Bienvenue sur e-Signification Bénin</h2>
          <p>Votre compte huissier a été créé par l'administrateur de la plateforme.</p>
          <p>Veuillez cliquer sur le lien ci-dessous pour compléter votre inscription :</p>
          <p style="margin:24px 0;">
            <a href="{lien}" style="background:#1a3c6e;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:500;">
              Activer mon compte
            </a>
          </p>
          <p style="color:#888;font-size:13px;">Ce lien est valable {settings.ACTIVATION_TOKEN_EXPIRY_HOURS} heures.</p>
          <p style="color:#888;font-size:12px;">Si vous n'attendiez pas cet email, ignorez-le.</p>
        </div>"""
    return envoyer_email(email, sujet, corps)


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
    from django.conf import settings
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    huissier = signification.huissier
    justiciable = signification.justiciable
    sujet = f"Certificat de signification — {signification.reference}"
    corps = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a3c6e;">Certificat de signification électronique</h2>
      <p>Référence : <strong>{signification.reference}</strong></p>
      <p>Acte réceptionné par : <strong>{justiciable.nom_complet}</strong></p>
      <p>Date et heure de réception : <strong>{certificat.date_reception.strftime('%d/%m/%Y à %Hh%Mm%Ss')}</strong> (heure de {certificat.timezone_reception})</p>
      <p>Ce certificat atteste que l'acte a été remis électroniquement à la date et heure indiquées.</p>
      <p style="color:#888;font-size:12px;">Vous pouvez consulter et télécharger ce certificat depuis votre espace sur la plateforme.</p>
    </div>"""
    envoyer_email(huissier.user.email, sujet, corps)
    envoyer_email(justiciable.email_domicile, sujet, corps)


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
