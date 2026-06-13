from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.http import HttpResponse, Http404
from django.utils.html import escape
from .models import Signification, CertificatSignification, ReponseJusticiable
from securite.audit import journaliser
from securite.chiffrement import chiffrer_fichier, dechiffrer_fichier, hash_fichier
import io


def _require_huissier(user):
    from accounts.models import User
    return user.role in [User.HUISSIER, User.CLERC]


def _require_justiciable(user):
    from accounts.models import User
    return user.role == User.JUSTICIABLE


@login_required
def envoyer_signification(request):
    if not _require_huissier(request.user):
        raise Http404
    from justiciables.models import ProfilJusticiable
    justiciable_uuid = request.GET.get('justiciable', '')
    justiciable = None
    if justiciable_uuid:
        try:
            justiciable = ProfilJusticiable.objects.get(uuid=justiciable_uuid, email_domicile_verifie=True)
        except ProfilJusticiable.DoesNotExist:
            pass
    if request.method == 'POST':
        j_uuid = escape(request.POST.get('justiciable_uuid', ''))
        necessite_reponse = request.POST.get('necessite_reponse') == 'on'
        fichier = request.FILES.get('fichier_acte')
        if not fichier or not j_uuid:
            from django.contrib import messages
            messages.error(request, "Veuillez sélectionner un justiciable et joindre l'acte.")
            return redirect(request.path)
        try:
            justiciable = ProfilJusticiable.objects.get(uuid=j_uuid)
        except ProfilJusticiable.DoesNotExist:
            raise Http404
        # Lire et chiffrer le fichier
        contenu = fichier.read()
        hash_acte = hash_fichier(contenu)
        contenu_chiffre = chiffrer_fichier(contenu)
        huissier = request.user.profil_huissier if hasattr(request.user, 'profil_huissier') else request.user.profil_clerc.huissier
        sig = Signification.objects.create(
            huissier=huissier,
            expediteur=request.user,
            justiciable=justiciable,
            fichier_chiffre=contenu_chiffre,
            nom_fichier_original=escape(fichier.name),
            taille_fichier=len(contenu),
            necessite_reponse=necessite_reponse,
            hash_acte=hash_acte,
        )
        # Envoyer l'email au justiciable
        from securite.tokens import creer_token_activation
        from accounts.models import TokenActivation
        token_accepter, _ = creer_token_activation(justiciable.email_domicile, TokenActivation.MFA_CODE, {'sig_uuid': str(sig.uuid), 'action': 'accepter'}, heures=72)
        token_refuser, _ = creer_token_activation(justiciable.email_domicile, TokenActivation.MFA_CODE, {'sig_uuid': str(sig.uuid), 'action': 'refuser'}, heures=72)
        from notifications.service import envoyer_signification as notif_sig
        notif_sig(justiciable, sig, token_accepter, token_refuser)
        journaliser(request.user, 'signification_envoyee', 'Signification', sig.uuid, request=request)
        from django.contrib import messages
        messages.success(request, f"Signification {sig.reference} envoyée avec succès.")
        return redirect('huissiers:tableau_de_bord')
    return render(request, 'significations/envoyer.html', {'justiciable': justiciable})


def repondre_signification(request, uuid):
    """Gère les clics Accepter/Refuser depuis l'email"""
    sig = get_object_or_404(Signification, uuid=uuid)
    action = request.GET.get('action', '')
    token_brut = request.GET.get('token', '')
    from securite.tokens import valider_token
    from accounts.models import TokenActivation
    token_obj, erreur = valider_token(token_brut, TokenActivation.MFA_CODE)
    if erreur or token_obj.metadata.get('sig_uuid') != str(uuid):
        return render(request, 'significations/lien_invalide.html')
    from securite.tokens import marquer_token_utilise
    marquer_token_utilise(token_obj)
    if action == 'accepter':
        sig.statut = Signification.STATUT_ACCEPTEE
        sig.date_acceptation = timezone.now()
        sig.save(update_fields=['statut', 'date_acceptation'])
        _generer_certificat(sig)
        journaliser(sig.justiciable.user, 'signification_acceptee', 'Signification', sig.uuid)
        # Rediriger vers connexion puis tableau de bord
        request.session['sig_acceptee_ref'] = sig.reference
        return redirect(f"/connexion/?next=/justiciable/")
    elif action == 'refuser':
        sig.statut = Signification.STATUT_REFUSEE
        sig.date_refus = timezone.now()
        sig.save(update_fields=['statut', 'date_refus'])
        journaliser(sig.justiciable.user, 'signification_refusee', 'Signification', sig.uuid)
        return render(request, 'significations/refus_confirme.html', {'sig': sig})
    return render(request, 'significations/lien_invalide.html')


def _generer_certificat(signification):
    """Génère le certificat de signification et l'horodate"""
    from securite.chiffrement import hash_fichier, chiffrer_fichier
    from securite.merkle import hash_noeud
    import hashlib
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    date_reception = timezone.now()
    # Hash unique du certificat
    hash_cert = hashlib.sha256(
        f"{signification.uuid}{date_reception.isoformat()}{signification.hash_acte}".encode()
    ).hexdigest()
    cert = CertificatSignification.objects.create(
        signification=signification,
        date_reception=date_reception,
        timezone_reception=str(timezone.get_current_timezone()),
        hash_certificat=hash_cert,
    )
    # Générer le PDF du certificat
    pdf_data = _generer_pdf_certificat(signification, cert)
    cert.fichier_certificat_chiffre = chiffrer_fichier(pdf_data)
    cert.save(update_fields=['fichier_certificat_chiffre'])
    # Notifier huissier et justiciable
    from notifications.service import envoyer_certificat
    envoyer_certificat(signification, cert)
    return cert


def _generer_pdf_certificat(signification, certificat):
    """Génère le PDF du certificat avec reportlab"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    # En-tête
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, h - 80, w, 80, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, h - 45, config.nom_plateforme)
    c.setFont("Helvetica", 11)
    c.drawString(40, h - 65, "Certificat de Signification Électronique")
    # Corps
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, h - 120, "CERTIFICAT DE SIGNIFICATION ÉLECTRONIQUE")
    y = h - 160
    c.setFont("Helvetica", 11)
    infos = [
        ("Référence", signification.reference),
        ("Huissier", f"Me {signification.huissier.prenom} {signification.huissier.nom}"),
        ("Étude", signification.huissier.nom_etude),
        ("Justiciable", signification.justiciable.nom_complet),
        ("Email domicile", signification.justiciable.email_domicile),
        ("Date de réception", certificat.date_reception.strftime('%d/%m/%Y')),
        ("Heure de réception", certificat.date_reception.strftime('%H:%M:%S')),
        ("Fuseau horaire", certificat.timezone_reception),
        ("Hash de l'acte", signification.hash_acte[:32] + "..."),
        ("Hash du certificat", certificat.hash_certificat[:32] + "..."),
    ]
    for label, valeur in infos:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, f"{label} :")
        c.setFont("Helvetica", 10)
        c.drawString(200, y, str(valeur))
        y -= 22
    if config.article_loi_signification:
        y -= 10
        c.setFont("Helvetica-Oblique", 9)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(40, y, f"Base légale : {config.article_loi_signification[:100]}")
    # Pied de page
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, 0, w, 40, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 8)
    c.drawString(40, 15, config.copyright_texte)
    c.drawString(w - 200, 15, f"Généré le {certificat.date_generation.strftime('%d/%m/%Y %H:%M:%S')}")
    c.showPage()
    c.save()
    return buffer.getvalue()


@login_required
def telecharger_acte(request, uuid):
    """Télécharge un acte déchiffré (justiciable uniquement)"""
    if not _require_justiciable(request.user):
        raise Http404
    sig = get_object_or_404(Signification, uuid=uuid, justiciable=request.user.profil_justiciable)
    if sig.statut not in [Signification.STATUT_ACCEPTEE, Signification.STATUT_REPONDU]:
        raise Http404
    contenu = dechiffrer_fichier(bytes(sig.fichier_chiffre))
    journaliser(request.user, 'acte_consulte', 'Signification', sig.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{sig.nom_fichier_original}"'
    return response


@login_required
def telecharger_certificat(request, uuid):
    cert = get_object_or_404(CertificatSignification, uuid=uuid)
    sig = cert.signification
    # Vérifier que l'utilisateur a le droit
    user = request.user
    from accounts.models import User as U
    if user.role == U.JUSTICIABLE and sig.justiciable != user.profil_justiciable:
        raise Http404
    if user.role in [U.HUISSIER, U.CLERC]:
        h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
        if sig.huissier != h:
            raise Http404
    contenu = dechiffrer_fichier(bytes(cert.fichier_certificat_chiffre))
    journaliser(user, 'certificat_telecharge', 'CertificatSignification', cert.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="certificat_{sig.reference}.pdf"'
    return response
