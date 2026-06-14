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

    # Recherche inline dans la page
    q = escape(request.GET.get('q', '').strip())
    resultats_recherche = []
    if q and len(q) >= 2 and not justiciable:
        from django.db.models import Q
        resultats_recherche = list(
            ProfilJusticiable.objects.filter(email_domicile_verifie=True).filter(
                Q(nom__icontains=q) | Q(prenom__icontains=q) |
                Q(ifu__icontains=q) | Q(npi__icontains=q) |
                Q(email_domicile__icontains=q)
            )[:15]
        )

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
        # Récupérer et valider la signature visuelle (base64 PNG)
        signature_b64 = request.POST.get('signature_b64', '').strip()
        if not signature_b64 or not signature_b64.startswith('data:image/png;base64,'):
            from django.contrib import messages
            messages.error(request, "Veuillez apposer votre signature avant d'envoyer l'acte.")
            return redirect(request.path)

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
            signature_huissier_b64=signature_b64,
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
    # Charger les signatures enregistrées de l'huissier
    from huissiers.models import ParametreSignatureHuissier
    huissier = (request.user.profil_huissier if hasattr(request.user, 'profil_huissier') and request.user.profil_huissier
                else getattr(getattr(request.user, 'profil_clerc', None), 'huissier', None))
    params_sig = None
    if huissier:
        params_sig, _ = ParametreSignatureHuissier.objects.get_or_create(huissier=huissier)
    return render(request, 'significations/envoyer.html', {
        'justiciable': justiciable,
        'q': q,
        'resultats_recherche': resultats_recherche,
        'params_sig': params_sig,
    })


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
    """Génère le PDF du certificat avec reportlab — logos officiels inclus"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from administration.models import ConfigurationPlateforme
    import os
    config = ConfigurationPlateforme.get()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # ── En-tête : bandeau bleu foncé ────────────────────────────────────────
    HEADER_H = 100
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, h - HEADER_H, w, HEADER_H, fill=1, stroke=0)

    # Logo pays — à gauche
    logo_x = 18
    if config.logo_pays and config.logo_pays.name:
        try:
            chemin_pays = config.logo_pays.path
            if os.path.isfile(chemin_pays):
                img_pays = ImageReader(chemin_pays)
                # Ajuster à 70x70 max en conservant le ratio
                iw, ih = img_pays.getSize()
                ratio = min(70 / iw, 70 / ih)
                rw, rh = iw * ratio, ih * ratio
                c.drawImage(img_pays, logo_x, h - HEADER_H + (HEADER_H - rh) / 2,
                            width=rw, height=rh, mask='auto', preserveAspectRatio=True)
                logo_x += rw + 10
        except Exception:
            pass  # Logo absent : on continue sans

    # Textes (titre + sous-titre) — centrés dans l'espace restant entre les logos
    # Logo chambre — à droite
    logo_chambre_x = w - 18
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
                c.drawImage(img_chambre, logo_chambre_x, h - HEADER_H + (HEADER_H - rh) / 2,
                            width=rw, height=rh, mask='auto', preserveAspectRatio=True)
                logo_chambre_w = rw + 10
        except Exception:
            pass

    # Textes centrés entre les deux logos
    texte_x_debut = logo_x + 6
    texte_largeur = (w - logo_chambre_w - 18) - texte_x_debut
    texte_centre = texte_x_debut + texte_largeur / 2
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(texte_centre, h - 40, config.nom_plateforme)
    c.setFont("Helvetica", 10)
    c.drawCentredString(texte_centre, h - 58, "CERTIFICAT DE SIGNIFICATION ELECTRONIQUE")
    c.setFont("Helvetica-Oblique", 8)
    c.drawCentredString(texte_centre, h - 73, f"Republique du {config.pays}")

    # ── Ligne de séparation décorative ──────────────────────────────────────
    c.setStrokeColorRGB(0.10, 0.24, 0.43)
    c.setLineWidth(1.5)
    c.line(40, h - HEADER_H - 18, w - 40, h - HEADER_H - 18)

    # ── Titre central du document ────────────────────────────────────────────
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(w / 2, h - HEADER_H - 40, "CERTIFICAT DE SIGNIFICATION ELECTRONIQUE")

    # ── Corps : tableau de données ───────────────────────────────────────────
    y = h - HEADER_H - 75
    c.setFont("Helvetica", 10)
    infos = [
        ("Reference",        signification.reference),
        ("Huissier",         f"Me {signification.huissier.prenom} {signification.huissier.nom}"),
        ("Etude",            signification.huissier.nom_etude),
        ("Justiciable",      signification.justiciable.nom_complet),
        ("Email domicile",   signification.justiciable.email_domicile),
        ("Date de reception", certificat.date_reception.strftime('%d/%m/%Y')),
        ("Heure de reception", certificat.date_reception.strftime('%H:%M:%S UTC')),
        ("Fuseau horaire",   certificat.timezone_reception),
        ("Hash de l'acte",   signification.hash_acte[:40] + "..." if signification.hash_acte else "N/A"),
        ("Hash du certificat", certificat.hash_certificat[:40] + "..." if certificat.hash_certificat else "N/A"),
    ]
    for i, (label, valeur) in enumerate(infos):
        # Alterner fond des lignes
        if i % 2 == 0:
            c.setFillColorRGB(0.96, 0.97, 0.99)
            c.rect(36, y - 5, w - 72, 20, fill=1, stroke=0)
        c.setFillColorRGB(0.10, 0.24, 0.43)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(42, y + 3, f"{label} :")
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("Helvetica", 9)
        c.drawString(210, y + 3, str(valeur))
        y -= 22

    # ── Base légale ──────────────────────────────────────────────────────────
    if config.article_loi_signification or config.decret_reference:
        y -= 10
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.5)
        c.line(40, y + 10, w - 40, y + 10)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Oblique", 8)
        if config.article_loi_signification:
            c.drawString(40, y - 2, f"Base legale : {config.article_loi_signification[:110]}")
            y -= 14
        if config.decret_reference:
            c.drawString(40, y - 2, f"Decret : {config.decret_reference[:120]}")

    # ── Signature visuelle de l'huissier ────────────────────────────────────
    if signification.signature_huissier_b64 and signification.signature_huissier_b64.startswith('data:image/png;base64,'):
        try:
            import base64
            from PIL import Image as PilImage
            b64_data = signification.signature_huissier_b64.split(',', 1)[1]
            img_bytes = base64.b64decode(b64_data)
            pil_img = PilImage.open(io.BytesIO(img_bytes)).convert('RGBA')
            # Fond blanc pour transparence
            bg = PilImage.new('RGBA', pil_img.size, (255, 255, 255, 255))
            bg.paste(pil_img, mask=pil_img.split()[3])
            sig_buf = io.BytesIO()
            bg.convert('RGB').save(sig_buf, format='PNG')
            sig_buf.seek(0)
            sig_img = ImageReader(sig_buf)
            # Zone de signature : à droite, au-dessus du pied de page
            sig_w, sig_h = 160, 55
            sig_x = w - 40 - sig_w
            sig_y_base = y - 60 if y > 100 else 55
            # Cadre
            c.setStrokeColorRGB(0.10, 0.24, 0.43)
            c.setLineWidth(0.8)
            c.rect(sig_x - 4, sig_y_base - 4, sig_w + 8, sig_h + 22, stroke=1, fill=0)
            # Label
            c.setFillColorRGB(0.10, 0.24, 0.43)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(sig_x, sig_y_base + sig_h + 6, "Signature de l'huissier instrumentaire :")
            # Image signature
            c.drawImage(sig_img, sig_x, sig_y_base, width=sig_w, height=sig_h,
                        preserveAspectRatio=True, mask='auto')
            # Nom sous la signature
            c.setFont("Helvetica-Oblique", 7)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.drawCentredString(sig_x + sig_w / 2, sig_y_base - 8,
                                f"Me {signification.huissier.prenom} {signification.huissier.nom}")
        except Exception:
            pass  # Signature absente ou corrompue — on continue sans

    # ── Mention d'authenticité ───────────────────────────────────────────────
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(w / 2, 55,
        "Ce certificat est genere automatiquement par la plateforme e-Signification Benin.")
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawCentredString(w / 2, 44,
        "Il constitue la preuve legale de la notification electronique de l'acte judiciaire.")

    # ── Pied de page : bandeau bleu ──────────────────────────────────────────
    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.rect(0, 0, w, 35, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica", 7)
    c.drawString(40, 13, config.copyright_texte)
    c.drawRightString(w - 40, 13,
        f"Genere le {certificat.date_generation.strftime('%d/%m/%Y a %H:%M:%S')}")

    c.showPage()
    c.save()
    return buffer.getvalue()


@login_required
def telecharger_acte(request, uuid):
    """Télécharge un acte déchiffré — justiciable (acte reçu) ou huissier/clerc (acte envoyé)"""
    user = request.user
    if _require_justiciable(user):
        # Le justiciable ne peut télécharger que si la signification lui est adressée et acceptée
        sig = get_object_or_404(Signification, uuid=uuid, justiciable=user.profil_justiciable)
        if sig.statut not in [Signification.STATUT_ACCEPTEE, Signification.STATUT_REPONDU]:
            raise Http404
    elif _require_huissier(user):
        # L'huissier/clerc peut télécharger tout acte de son étude
        from accounts.models import User as _User
        huissier = (user.profil_huissier if user.role == _User.HUISSIER
                    else user.profil_clerc.huissier)
        sig = get_object_or_404(Signification, uuid=uuid, huissier=huissier)
    else:
        raise Http404
    contenu = dechiffrer_fichier(bytes(sig.fichier_chiffre))
    journaliser(user, 'acte_consulte', 'Signification', sig.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{sig.nom_fichier_original}"'
    return response


@login_required
def voir_reponse(request, uuid):
    """Permet à l'huissier de consulter la réponse du justiciable"""
    sig = get_object_or_404(Signification, uuid=uuid)
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    if sig.statut != Signification.STATUT_REPONDU or not hasattr(sig, 'reponse'):
        raise Http404
    reponse = sig.reponse
    if not reponse.vue_par_huissier:
        reponse.vue_par_huissier = True
        from django.utils import timezone as tz
        reponse.date_reception_huissier = tz.now()
        reponse.save(update_fields=['vue_par_huissier', 'date_reception_huissier'])
        journaliser(request.user, 'reponse_consultee', 'ReponseJusticiable', reponse.uuid, request=request)
    fichier_disponible = bool(reponse.fichier_reponse_chiffre)
    return render(request, 'significations/voir_reponse.html', {
        'sig': sig, 'reponse': reponse, 'fichier_disponible': fichier_disponible,
    })


@login_required
def telecharger_reponse(request, uuid):
    """Télécharge le fichier de réponse (huissier uniquement)"""
    sig = get_object_or_404(Signification, uuid=uuid)
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    if not hasattr(sig, 'reponse') or not sig.reponse.fichier_reponse_chiffre:
        raise Http404
    reponse = sig.reponse
    contenu = dechiffrer_fichier(bytes(reponse.fichier_reponse_chiffre))
    journaliser(request.user, 'reponse_telechargee', 'ReponseJusticiable', reponse.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{reponse.nom_fichier_reponse or "reponse.pdf"}"'
    return response


@login_required
@require_http_methods(["POST"])
def basculer_traditionnel(request, uuid):
    """Bascule une signification en mode traditionnel"""
    sig = get_object_or_404(Signification, uuid=uuid)
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    if sig.statut not in [Signification.STATUT_EN_ATTENTE,
                          Signification.STATUT_RELANCE_1,
                          Signification.STATUT_RELANCE_2]:
        from django.contrib import messages
        messages.error(request, "Ce statut ne permet pas de basculer en traditionnel.")
        return redirect('huissiers:significations')
    sig.statut = Signification.STATUT_TRADITIONNELLE
    sig.save(update_fields=['statut'])
    journaliser(request.user, 'signification_basculee_traditionnelle', 'Signification', sig.uuid, request=request)
    from django.contrib import messages
    messages.success(request, f"La signification {sig.reference} a été basculée en mode traditionnel.")
    return redirect('huissiers:significations')


@login_required
def telecharger_constat(request, uuid):
    """Télécharge le constat de non-réception (huissier uniquement)"""
    sig = get_object_or_404(Signification, uuid=uuid)
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    relance = sig.relances.filter(numero_relance=2).first()
    if not relance or not relance.constat_chiffre:
        raise Http404
    contenu = dechiffrer_fichier(bytes(relance.constat_chiffre))
    journaliser(request.user, 'constat_telecharge', 'Signification', sig.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="constat_{sig.reference}.pdf"'
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
