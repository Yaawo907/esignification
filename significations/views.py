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


def _get_huissier_utilisateur(user):
    if hasattr(user, 'profil_huissier') and user.profil_huissier:
        return user.profil_huissier
    return getattr(getattr(user, 'profil_clerc', None), 'huissier', None)


def _signatures_autorisees_huissier(huissier):
    from huissiers.models import ParametreSignatureHuissier
    try:
        params = ParametreSignatureHuissier.objects.get(huissier=huissier)
    except ParametreSignatureHuissier.DoesNotExist:
        return []
    return [
        v.strip() for v in (
            params.signature_simple_b64,
            params.signature_cachet_b64,
            params.cachet_simple_b64,
        ) if v and v.strip()
    ]


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
        titre_acte = escape(request.POST.get('titre_acte', '').strip())
        necessite_reponse = request.POST.get('necessite_reponse') == 'on'
        fichier = request.FILES.get('fichier_acte')
        from django.contrib import messages
        redirect_url = f"{request.path}?justiciable={j_uuid}" if j_uuid else request.path
        if not titre_acte or len(titre_acte) < 3:
            messages.error(request, "Veuillez saisir le titre de l'acte (minimum 3 caractères).")
            return redirect(redirect_url)
        if not fichier or not j_uuid:
            messages.error(request, "Veuillez sélectionner un justiciable et joindre l'acte.")
            return redirect(redirect_url)
        try:
            justiciable = ProfilJusticiable.objects.get(uuid=j_uuid)
        except ProfilJusticiable.DoesNotExist:
            raise Http404

        from accounts.models import User as UserModel
        huissier = _get_huissier_utilisateur(request.user)
        est_clerc = request.user.role == UserModel.CLERC

        # Récupérer et valider la signature visuelle (tout format image base64)
        signature_b64 = request.POST.get('signature_b64', '').strip()
        prefixes_valides = (
            'data:image/png;base64,', 'data:image/jpeg;base64,',
            'data:image/jpg;base64,', 'data:image/svg+xml;base64,',
            'data:image/webp;base64,', 'data:image/gif;base64,',
        )
        if not signature_b64 or not any(signature_b64.startswith(p) for p in prefixes_valides):
            messages.error(request, "Veuillez apposer votre signature avant d'envoyer l'acte.")
            return redirect(redirect_url)

        if est_clerc:
            autorisees = _signatures_autorisees_huissier(huissier)
            if not autorisees:
                messages.error(
                    request,
                    "Aucun tampon n'est configuré pour l'étude. Contactez l'huissier titulaire.",
                )
                return redirect(redirect_url)
            if signature_b64 not in autorisees:
                messages.error(
                    request,
                    "En tant que clerc, vous devez choisir un tampon configuré par l'étude.",
                )
                return redirect(redirect_url)

        # Lire et chiffrer le fichier
        contenu = fichier.read()
        hash_acte = hash_fichier(contenu)
        contenu_chiffre = chiffrer_fichier(contenu)

        from paiements.services.credits import verifier_solde_envoi, debiter_envoi_signification, CreditInsuffisant
        try:
            verifier_solde_envoi(huissier)
        except CreditInsuffisant as exc:
            from django.contrib import messages
            messages.error(
                request,
                f"Crédits insuffisants (solde : {exc.solde}, requis : {exc.requis}). "
                f"Rechargez votre solde avant d'envoyer une signification."
            )
            return redirect('paiements:achat_credits')

        from administration.models import ConfigurationPlateforme as _CP
        yousign_actif = _CP.get().yousign_active

        placement_yousign = None
        if yousign_actif:
            from notifications.sms import normaliser_telephone_yousign
            from .yousign_placement import extraire_placement_post, valider_placement_yousign
            try:
                normaliser_telephone_yousign(huissier.telephone)
            except ValueError as exc:
                from django.contrib import messages
                messages.error(request, str(exc))
                return redirect(request.path)
            try:
                placement_yousign = valider_placement_yousign(
                    contenu,
                    extraire_placement_post(request.POST),
                )
            except ValueError as exc:
                from django.contrib import messages
                messages.error(request, str(exc))
                return redirect(request.path)

        # Statut initial : si Yousign actif, l'acte attend la signature de l'huissier
        statut_initial = (Signification.STATUT_ATTENTE_SIGNATURE if yousign_actif
                         else Signification.STATUT_EN_ATTENTE)

        sig = Signification.objects.create(
            huissier=huissier,
            expediteur=request.user,
            justiciable=justiciable,
            fichier_chiffre=contenu_chiffre,
            nom_fichier_original=escape(fichier.name),
            titre_acte=titre_acte,
            taille_fichier=len(contenu),
            necessite_reponse=necessite_reponse,
            hash_acte=hash_acte,
            signature_huissier_b64=signature_b64,
            statut=statut_initial,
        )

        from django.contrib import messages

        if yousign_actif:
            # ── FLUX YOUSIGN ──
            # L'acte n'est PAS encore envoyé au justiciable.
            # Yousign envoie un lien par email ; l'OTP SMS autorise la signature.
            # Dès que l'huissier signe, le webhook déclenche l'envoi au justiciable.
            yousign_ok, yousign_err = _lancer_yousign_si_actif(sig, contenu, placement_yousign)
            if yousign_ok:
                journaliser(request.user, 'signification_attente_signature_yousign',
                            'Signification', sig.uuid, request=request)
                messages.success(
                    request,
                    f"Acte {sig.reference} préparé. Vérifiez votre email : Yousign vous a envoyé "
                    f"un lien pour signer. Un code OTP vous sera transmis par SMS au moment "
                    f"de la signature. L'acte sera transmis au justiciable dès votre signature."
                )
            elif yousign_err:
                sig.delete()
                messages.error(request, yousign_err)
                return redirect(request.path)
            else:
                # Échec Yousign : fallback envoi direct
                sig.statut = Signification.STATUT_EN_ATTENTE
                sig.save(update_fields=['statut'])
                _envoyer_au_justiciable(sig, justiciable)
                journaliser(request.user, 'signification_envoyee', 'Signification', sig.uuid, request=request)
                messages.warning(
                    request,
                    f"Signification {sig.reference} envoyée directement (Yousign indisponible)."
                )
        else:
            # ── FLUX CLASSIQUE ──
            _envoyer_au_justiciable(sig, justiciable)
            journaliser(request.user, 'signification_envoyee', 'Signification', sig.uuid, request=request)
            messages.success(request, f"Signification {sig.reference} envoyée avec succès.")

        debiter_envoi_signification(sig, request.user)
        if yousign_actif and placement_yousign:
            from .yousign_placement import sauvegarder_dimensions_profil_huissier
            sauvegarder_dimensions_profil_huissier(huissier, placement_yousign)
        return redirect('huissiers:tableau_de_bord')
    # Charger les signatures enregistrées de l'huissier
    from accounts.models import User as UserModel
    from huissiers.models import ParametreSignatureHuissier
    huissier = _get_huissier_utilisateur(request.user)
    est_clerc = request.user.role == UserModel.CLERC
    params_sig = None
    if huissier:
        params_sig, _ = ParametreSignatureHuissier.objects.get_or_create(huissier=huissier)
    from paiements.services.credits import get_solde, credit_debit_envoi, cout_net_apres_refus, cout_net_apres_annulation
    from administration.models import ConfigurationPlateforme
    config = ConfigurationPlateforme.get()
    solde_credits = get_solde(huissier) if huissier else None
    signatures_configurees = bool(_signatures_autorisees_huissier(huissier)) if huissier else False
    return render(request, 'significations/envoyer.html', {
        'justiciable': justiciable,
        'q': q,
        'resultats_recherche': resultats_recherche,
        'params_sig': params_sig,
        'est_clerc': est_clerc,
        'signatures_configurees': signatures_configurees,
        'solde_credits': solde_credits,
        'credit_debit_envoi': credit_debit_envoi(),
        'credit_retour_refus': credit_debit_envoi() - cout_net_apres_refus(),
        'credit_retour_annulation': credit_debit_envoi() - cout_net_apres_annulation(),
        'prix_credit_fcfa': config.prix_credit_fcfa,
        'yousign_actif': config.yousign_active,
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
        from paiements.services.credits import rembourser_selon_reponse_client
        rembourser_selon_reponse_client(sig, Signification.STATUT_ACCEPTEE)
        _generer_certificat(sig)
        journaliser(sig.justiciable.user, 'signification_acceptee', 'Signification', sig.uuid)
        # Rediriger vers connexion avec email pré-rempli
        request.session['sig_acceptee_ref'] = sig.reference
        email_justiciable = sig.justiciable.user.email
        from urllib.parse import urlencode
        params = urlencode({'next': '/justiciable/', 'email': email_justiciable})
        return redirect(f"/connexion/?{params}")
    elif action == 'refuser':
        sig.statut = Signification.STATUT_REFUSEE
        sig.date_refus = timezone.now()
        sig.save(update_fields=['statut', 'date_refus'])
        from paiements.services.credits import rembourser_selon_reponse_client
        rembourser_selon_reponse_client(sig, Signification.STATUT_REFUSEE)
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
    from django.utils import timezone as tz_util
    date_rec = certificat.date_reception
    if tz_util.is_aware(date_rec):
        date_rec = tz_util.localtime(date_rec)
    date_reception_fmt = date_rec.strftime('%d/%m/%Y à %Hh%Mm%Ss')
    tz_label = certificat.timezone_reception or 'Africa/Porto-Novo'

    y = h - HEADER_H - 75
    c.setFont("Helvetica", 10)
    infos = [
        ("Reference",        signification.reference),
        ("Huissier",         f"Me {signification.huissier.prenom} {signification.huissier.nom}"),
        ("Etude",            signification.huissier.nom_etude),
        ("Justiciable",      signification.justiciable.nom_complet),
        ("Email domicile",   signification.justiciable.email_domicile),
        ("Date et heure de reception", f"{date_reception_fmt} ({tz_label})"),
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

    # ── Attestation ──────────────────────────────────────────────────────────
    y -= 8
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.setFont("Helvetica", 10)
    attestation = (
        "Ce certificat atteste que l'acte a ete remis electroniquement "
        "a la date et heure indiquees ci-dessus."
    )
    c.drawString(40, y, attestation)
    y -= 28  # espace avant la zone de signature

    # ── Base légale ──────────────────────────────────────────────────────────
    if config.article_loi_signification or config.decret_reference:
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.5)
        c.line(40, y + 10, w - 40, y + 10)
        y -= 6
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.setFont("Helvetica-Oblique", 8)
        if config.article_loi_signification:
            c.drawString(40, y, f"Base legale : {config.article_loi_signification[:110]}")
            y -= 14
        if config.decret_reference:
            c.drawString(40, y, f"Decret : {config.decret_reference[:120]}")
            y -= 14
        y -= 10

    # ── Signature visuelle de l'huissier ────────────────────────────────────
    _PREFIXES_IMG = (
        'data:image/png;base64,', 'data:image/jpeg;base64,',
        'data:image/jpg;base64,', 'data:image/webp;base64,',
        'data:image/gif;base64,', 'data:image/svg+xml;base64,',
    )
    if signification.signature_huissier_b64 and any(
            signification.signature_huissier_b64.startswith(p) for p in _PREFIXES_IMG):
        try:
            import base64
            from PIL import Image as PilImage
            b64_data = signification.signature_huissier_b64.split(',', 1)[1]
            img_bytes = base64.b64decode(b64_data)
            pil_img = PilImage.open(io.BytesIO(img_bytes))
            if pil_img.mode != 'RGBA':
                pil_img = pil_img.convert('RGBA')
            bg = PilImage.new('RGBA', pil_img.size, (255, 255, 255, 255))
            bg.paste(pil_img, mask=pil_img.split()[3])
            sig_buf = io.BytesIO()
            bg.convert('RGB').save(sig_buf, format='PNG')
            sig_buf.seek(0)
            sig_img = ImageReader(sig_buf)
            sig_w, sig_h = 160, 55
            sig_x = w - 40 - sig_w
            pad = 6
            frame_h = sig_h + pad * 2

            # Label au-dessus du cadre
            c.setFillColorRGB(0.10, 0.24, 0.43)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(sig_x, y, "Signature de l'huissier instrumentaire :")
            y -= 12

            # Cadre puis image à l'intérieur
            frame_y = y - frame_h
            c.setStrokeColorRGB(0.10, 0.24, 0.43)
            c.setLineWidth(0.8)
            c.rect(sig_x - 4, frame_y, sig_w + 8, frame_h, stroke=1, fill=0)
            c.drawImage(sig_img, sig_x, frame_y + pad, width=sig_w, height=sig_h,
                        preserveAspectRatio=True, mask='auto')

            # Nom de l'huissier sous le cadre
            c.setFont("Helvetica-Oblique", 7)
            c.setFillColorRGB(0.3, 0.3, 0.3)
            c.drawCentredString(sig_x + sig_w / 2, frame_y - 10,
                                f"Me {signification.huissier.prenom} {signification.huissier.nom}")
        except Exception:
            pass

    # Mention Yousign sur le certificat si signature complète
    if signification.yousign_statut == 'done':
        c.setFillColorRGB(0.05, 0.45, 0.15)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(w / 2, 62,
            "✓ Acte signé numériquement (Signature Électronique Avancée — Yousign)")

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
def detail_signification(request, uuid):
    """Fiche détail imprimable d'une signification — huissier / clerc."""
    sig = get_object_or_404(
        Signification.objects.select_related(
            'huissier', 'justiciable', 'expediteur', 'certificat',
        ).prefetch_related('relances'),
        uuid=uuid,
    )
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    date_edition = timezone.localtime(timezone.now())
    journaliser(
        request.user, 'signification_detail_consulte', 'Signification',
        sig.uuid, description=f"Détail — {sig.reference}", request=request,
    )
    reponse = None
    if hasattr(sig, 'reponse'):
        reponse = sig.reponse
    return render(request, 'significations/detail_signification.html', {
        'sig': sig,
        'reponse': reponse,
        'date_edition': date_edition,
    })


@login_required
def telecharger_acte(request, uuid):
    """Télécharge un acte déchiffré — justiciable (acte reçu) ou huissier/clerc (acte envoyé)"""
    user = request.user
    if _require_justiciable(user):
        sig = get_object_or_404(Signification, uuid=uuid, justiciable=user.profil_justiciable)
        if sig.statut not in [Signification.STATUT_ACCEPTEE, Signification.STATUT_REPONDU]:
            raise Http404
    elif _require_huissier(user):
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
def telecharger_preuve_yousign(request, uuid):
    """Télécharge le dossier de preuve Yousign (audit trail) — huissier/clerc uniquement."""
    user = request.user
    if not _require_huissier(user):
        raise Http404
    from accounts.models import User as _User
    huissier = (user.profil_huissier if user.role == _User.HUISSIER
                else user.profil_clerc.huissier)
    sig = get_object_or_404(Signification, uuid=uuid, huissier=huissier)
    if not sig.yousign_audit_trail_chiffre:
        raise Http404
    contenu = dechiffrer_fichier(bytes(sig.yousign_audit_trail_chiffre))
    journaliser(user, 'preuve_yousign_telechargee', 'Signification', sig.uuid, request=request)
    response = HttpResponse(contenu, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="preuve_yousign_{sig.reference}.pdf"'
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
    reponse = get_object_or_404(
        ReponseJusticiable.objects.select_related('lot_merkle'),
        signification=sig,
    )
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
                          Signification.STATUT_ATTENTE_SIGNATURE,
                          Signification.STATUT_RELANCE_1,
                          Signification.STATUT_RELANCE_2]:
        from django.contrib import messages
        messages.error(request, "Ce statut ne permet pas de basculer en traditionnel.")
        return redirect('huissiers:significations')
    sig.statut = Signification.STATUT_TRADITIONNELLE
    sig.save(update_fields=['statut'])
    from paiements.services.credits import rembourser_selon_reponse_client
    rembourser_selon_reponse_client(sig, Signification.STATUT_TRADITIONNELLE, auteur=request.user)
    journaliser(request.user, 'signification_basculee_traditionnelle', 'Signification', sig.uuid, request=request)
    from django.contrib import messages
    messages.success(request, f"La signification {sig.reference} a été basculée en mode traditionnel.")
    return redirect('huissiers:significations')


@login_required
@require_http_methods(["POST"])
def annuler_signification(request, uuid):
    """Annule une signification en cours — retour de crédit selon tarif annulation."""
    sig = get_object_or_404(Signification, uuid=uuid)
    user = request.user
    from accounts.models import User as U
    if user.role not in [U.HUISSIER, U.CLERC]:
        raise Http404
    h = user.profil_huissier if user.role == U.HUISSIER else user.profil_clerc.huissier
    if sig.huissier != h:
        raise Http404
    if sig.statut not in (
        Signification.STATUT_EN_ATTENTE,
        Signification.STATUT_ATTENTE_SIGNATURE,
        Signification.STATUT_RELANCE_1,
        Signification.STATUT_RELANCE_2,
    ):
        from django.contrib import messages
        messages.error(request, "Cette signification ne peut plus être annulée.")
        return redirect('huissiers:significations')
    sig.statut = Signification.STATUT_ANNULEE
    sig.save(update_fields=['statut'])
    from paiements.services.credits import rembourser_selon_reponse_client
    rembourser_selon_reponse_client(sig, Signification.STATUT_ANNULEE, auteur=request.user)
    journaliser(request.user, 'signification_annulee', 'Signification', sig.uuid, request=request)
    from django.contrib import messages
    messages.success(request, f"Signification {sig.reference} annulée.")
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



# ─────────────────────────────────────────────────────────────
#  Yousign — helpers
# ─────────────────────────────────────────────────────────────

def _envoyer_au_justiciable(sig, justiciable):
    """Crée les tokens accepter/refuser et notifie le justiciable par email."""
    from securite.tokens import creer_token_activation
    from accounts.models import TokenActivation
    from notifications.service import envoyer_signification as notif_sig
    token_accepter, _ = creer_token_activation(
        justiciable.email_domicile, TokenActivation.MFA_CODE,
        {'sig_uuid': str(sig.uuid), 'action': 'accepter'}, heures=72,
    )
    token_refuser, _ = creer_token_activation(
        justiciable.email_domicile, TokenActivation.MFA_CODE,
        {'sig_uuid': str(sig.uuid), 'action': 'refuser'}, heures=72,
    )
    notif_sig(justiciable, sig, token_accepter, token_refuser)


def finaliser_yousign_et_envoyer_justiciable(sig, sig_req_id=None):
    """
    Télécharge le PDF signé, met à jour la signification et notifie le justiciable.
    Appelé par le webhook Yousign ou par synchronisation manuelle (dev local).
    """
    import logging
    logger = logging.getLogger(__name__)
    sig_req_id = sig_req_id or sig.yousign_signature_request_id
    if not sig_req_id:
        raise ValueError("Aucune demande Yousign associée à cette signification.")

    if sig.yousign_statut == 'done' and sig.statut == Signification.STATUT_EN_ATTENTE:
        logger.info("Yousign : %s déjà finalisée, envoi justiciable uniquement.", sig.reference)
        _envoyer_au_justiciable(sig, sig.justiciable)
        return

    try:
        from .yousign_service import telecharger_document_signe, telecharger_audit_trail
        pdf_signe = telecharger_document_signe(sig_req_id)
        sig.fichier_chiffre = chiffrer_fichier(pdf_signe)
        audit_trail_pdf = None
        try:
            audit_trail_pdf = telecharger_audit_trail(sig_req_id, sig.yousign_signer_id or None)
            sig.yousign_audit_trail_chiffre = chiffrer_fichier(audit_trail_pdf)
            if not sig.yousign_signer_id:
                from .yousign_service import recuperer_signataire_id
                sig.yousign_signer_id = recuperer_signataire_id(sig_req_id)
        except Exception as e:
            logger.warning("Yousign : audit trail non recupere pour %s — %s", sig.reference, e)
    except Exception as e:
        logger.error("Yousign : PDF signé non récupéré pour %s — %s", sig.reference, e)
        raise

    sig.yousign_statut = 'done'
    sig.statut = Signification.STATUT_EN_ATTENTE
    update_fields = ['yousign_statut', 'statut', 'fichier_chiffre']
    if sig.yousign_audit_trail_chiffre:
        update_fields.append('yousign_audit_trail_chiffre')
    if sig.yousign_signer_id:
        update_fields.append('yousign_signer_id')
    sig.save(update_fields=update_fields)

    journaliser(None, 'yousign_signature_done', 'Signification', sig.uuid,
                description=f"Signature Yousign complete : {sig_req_id}")

    from notifications.service import envoyer_preuve_yousign_huissier
    envoyer_preuve_yousign_huissier(sig, pdf_signe, audit_trail_pdf)
    _envoyer_au_justiciable(sig, sig.justiciable)
    journaliser(None, 'signification_envoyee_apres_signature', 'Signification', sig.uuid,
                description="Acte transmis au justiciable après signature Yousign")


def synchroniser_signification_yousign(sig):
    """
    Interroge Yousign et finalise si la signature est terminée.
    Retourne (succes: bool, message: str).
    """
    if sig.statut != Signification.STATUT_ATTENTE_SIGNATURE:
        return False, "Cette signification n'est pas en attente de signature huissier."
    sig_req_id = sig.yousign_signature_request_id
    if not sig_req_id:
        return False, "Aucune demande Yousign associée à cette signification."

    from .yousign_service import recuperer_statut_yousign
    statut_ys = recuperer_statut_yousign(sig_req_id)
    if statut_ys == 'done':
        finaliser_yousign_et_envoyer_justiciable(sig, sig_req_id)
        return True, "Signature confirmée. L'acte a été transmis au justiciable."
    return False, f"Signature Yousign en cours (statut API : {statut_ys or 'inconnu'})."


def _lancer_yousign_si_actif(signification, pdf_bytes, placement=None) -> tuple[bool, str]:
    """
    Lance la demande de signature Yousign pour l'huissier.
    Retourne (True, '') si succès, (False, message) si erreur bloquante,
    (False, '') si échec technique (fallback possible).
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from .yousign_service import creer_demande_signature
        sig_req_id = creer_demande_signature(signification, pdf_bytes, placement=placement)
        journaliser(None, 'yousign_demande_creee', 'Signification', signification.uuid,
                    description=f"Signature request Yousign : {sig_req_id}")
        return True, ''
    except ValueError as e:
        logger.error("Yousign : numero invalide pour %s — %s", signification.reference, e)
        return False, str(e)
    except Exception as e:
        err = str(e)
        logger.error("Yousign : echec pour %s — %s", signification.reference, e)
        from .yousign_service import message_erreur_yousign_api
        msg = message_erreur_yousign_api(err)
        if msg:
            return False, msg
        return False, ''


def synchroniser_signification_yousign(sig):
    """
    Interroge l'API Yousign et finalise l'envoi au justiciable si la signature est terminée.
    Retourne (succes: bool, message: str).
    """
    if sig.statut != Signification.STATUT_ATTENTE_SIGNATURE:
        return False, "Cette signification n'est pas en attente de signature huissier."
    sig_req_id = (sig.yousign_signature_request_id or '').strip()
    if not sig_req_id:
        return False, "Aucune demande Yousign associée à cette signification."

    from .yousign_service import recuperer_statut_yousign
    try:
        statut_ys = recuperer_statut_yousign(sig_req_id)
    except Exception as exc:
        return False, f"Impossible de contacter Yousign : {exc}"

    if statut_ys == 'done':
        try:
            finaliser_yousign_et_envoyer_justiciable(sig, sig_req_id)
        except Exception as exc:
            return False, f"Signature confirmée mais échec de finalisation : {exc}"
        return True, "Signature confirmée. L'acte a été transmis au justiciable."

    return False, f"Signature Yousign en cours (statut API : {statut_ys or 'inconnu'})."


@login_required
@require_http_methods(["POST"])
def synchroniser_yousign(request, uuid):
    """Rattrapage manuel si le webhook Yousign n'a pas été reçu."""
    if not _require_huissier(request.user):
        raise Http404

    from accounts.models import User
    huissier = (
        request.user.profil_huissier
        if request.user.role == User.HUISSIER
        else request.user.profil_clerc.huissier
    )
    sig = get_object_or_404(Signification, uuid=uuid, huissier=huissier)

    ok, message = synchroniser_signification_yousign(sig)
    from django.contrib import messages
    if ok:
        sig.refresh_from_db()
        journaliser(request.user, 'yousign_sync_manuelle', 'Signification', sig.uuid, request=request)
        messages.success(request, message)
    else:
        messages.warning(request, message)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        from django.http import JsonResponse
        return JsonResponse({'ok': ok, 'message': message, 'statut': sig.statut})

    return redirect('huissiers:significations')


# ─────────────────────────────────────────────────────────────
#  Yousign — Webhook
# ─────────────────────────────────────────────────────────────

from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook_yousign(request):
    if request.method == 'GET':
        return HttpResponse('Yousign webhook OK', content_type='text/plain')

    import json as _json
    import logging
    logger = logging.getLogger(__name__)

    payload_bytes = request.body
    sig_header = request.headers.get('X-Yousign-Signature-256', '')

    try:
        from .yousign_service import valider_webhook
        if not valider_webhook(payload_bytes, sig_header):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Signature invalide")
    except Exception as e:
        logger.error("Webhook Yousign : erreur validation — %s", e)
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden("Erreur validation")

    try:
        data = _json.loads(payload_bytes)
    except Exception:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("JSON invalide")

    event_name = data.get('event_name', '')
    from .yousign_service import extraire_signature_request_id
    sig_req_id = extraire_signature_request_id(data)

    logger.info("Webhook Yousign : %s — request_id=%s", event_name, sig_req_id)

    if not sig_req_id:
        return HttpResponse(status=200)

    try:
        sig = Signification.objects.get(yousign_signature_request_id=sig_req_id)
    except Signification.DoesNotExist:
        logger.warning("Webhook Yousign : signification introuvable pour %s", sig_req_id)
        return HttpResponse(status=200)

    if event_name == 'signature_request.done':
        try:
            finaliser_yousign_et_envoyer_justiciable(sig, sig_req_id)
        except Exception as e:
            logger.error("Webhook Yousign : erreur finalisation — %s", e, exc_info=True)
            return HttpResponse(status=500)

    elif event_name in ('signature_request.expired', 'signature_request.canceled',
                        'signature_request.rejected'):
        nouveau_statut = event_name.split('.')[1]
        sig.yousign_statut = nouveau_statut
        sig.save(update_fields=['yousign_statut'])
        journaliser(None, f'yousign_{nouveau_statut}', 'Signification', sig.uuid,
                    description=f"Yousign {nouveau_statut} : {sig_req_id}")
        try:
            from notifications.service import envoyer_yousign_expiree
            envoyer_yousign_expiree(sig, nouveau_statut)
        except Exception as e:
            logger.error("Webhook Yousign : notification echec huissier — %s", e)

    return HttpResponse(status=200)

