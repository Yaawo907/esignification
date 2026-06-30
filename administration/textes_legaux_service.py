"""Enregistrement et vérification des acceptations CGU / politique de confidentialité."""
import hashlib
import io

from django.utils import timezone, translation

from .models import AcceptationTexteLegal, ConfigurationPlateforme, TexteLegal

TYPES_OBLIGATOIRES = (TexteLegal.TYPE_CGU, TexteLegal.TYPE_CONFIDENTIALITE)


def _langue_utilisateur(user=None, langue=None):
    if langue:
        return langue.split('-')[0].lower()
    if user and hasattr(user, 'langue_preferee') and user.langue_preferee:
        return user.langue_preferee
    return (translation.get_language() or 'fr').split('-')[0].lower()


def _hash_contenu(contenu_html: str) -> str:
    return hashlib.sha256((contenu_html or '').encode('utf-8')).hexdigest()


def get_texte_legal_actif(type_texte: str, langue: str = 'fr'):
    return (
        TexteLegal.objects.filter(type_texte=type_texte, langue=langue, actif=True).first()
        or TexteLegal.objects.filter(type_texte=type_texte, actif=True).order_by('langue').first()
    )


def _meta_requete(request):
    if not request:
        return None, ''
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')
    ua = request.META.get('HTTP_USER_AGENT', '')[:500]
    return ip, ua


def _derniere_acceptation_valide(user, type_texte: str, langue: str):
    texte = get_texte_legal_actif(type_texte, langue)
    if not texte:
        return True, None
    derniere = (
        AcceptationTexteLegal.objects
        .filter(user=user, type_texte=type_texte, langue=texte.langue)
        .order_by('-date_acceptation')
        .first()
    )
    if not derniere:
        return False, texte
    hash_courant = _hash_contenu(texte.contenu_html)
    if derniere.version == texte.version and derniere.hash_contenu == hash_courant:
        return True, texte
    return False, texte


def textes_a_reaccepter(user, langue=None):
    """Textes légaux actifs non acceptés à la version courante."""
    if not user or not user.is_authenticated:
        return []
    if getattr(user, 'role', None) == user.ADMIN:
        return []
    langue = _langue_utilisateur(user, langue)
    manquants = []
    for type_texte in TYPES_OBLIGATOIRES:
        accepte, texte = _derniere_acceptation_valide(user, type_texte, langue)
        if not accepte and texte:
            manquants.append(texte)
    return manquants


def utilisateur_a_accepte_textes_courants(user, langue=None) -> bool:
    return not textes_a_reaccepter(user, langue=langue)


def enregistrer_acceptations(user, request, contexte: str, langue=None):
    """Enregistre l'acceptation de chaque texte légal obligatoire actif."""
    from securite.audit import journaliser

    langue = _langue_utilisateur(user, langue)
    ip, ua = _meta_requete(request)
    enregistrees = []

    for type_texte in TYPES_OBLIGATOIRES:
        texte = get_texte_legal_actif(type_texte, langue)
        if not texte:
            continue
        hash_contenu = _hash_contenu(texte.contenu_html)
        acceptation = AcceptationTexteLegal.objects.create(
            user=user,
            texte_legal=texte,
            type_texte=type_texte,
            version=texte.version,
            langue=texte.langue,
            hash_contenu=hash_contenu,
            contexte=contexte,
            ip_address=ip,
            user_agent=ua,
        )
        enregistrees.append(acceptation)
        journaliser(
            user,
            'acceptation_texte_legal',
            objet_type='AcceptationTexteLegal',
            objet_uuid=acceptation.uuid,
            description=(
                f"{texte.get_type_texte_display()} v{texte.version} "
                f"({texte.langue}) — contexte: {contexte}"
            ),
            request=request,
        )
    return enregistrees


def libelle_utilisateur(user) -> str:
    """Nom affichable pour les preuves (huissier, clerc, justiciable)."""
    if not user:
        return ''
    profil = user.get_profil()
    if profil:
        nom = getattr(profil, 'nom', '') or ''
        prenom = getattr(profil, 'prenom', '') or ''
        label = f'{prenom} {nom}'.strip()
        if label:
            if getattr(profil, 'nom_etude', ''):
                return f'{label} — {profil.nom_etude}'
            return label
    return user.email


def libelle_role(user) -> str:
    if not user:
        return ''
    return dict(user.ROLE_CHOICES).get(user.role, user.role)


def _formater_datetime(dt) -> tuple[str, str]:
    if not dt:
        return '—', '—'
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.strftime('%d/%m/%Y'), dt.strftime('%H:%M:%S')


def _dessiner_preuve_pdf(acceptations, titre_document: str, reference: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    config = ConfigurationPlateforme.get()
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4
    marge = 45
    y = h - 50

    c.setFillColorRGB(0.10, 0.24, 0.43)
    c.setFont('Helvetica-Bold', 14)
    c.drawCentredString(w / 2, y, config.nom_plateforme)
    y -= 18
    c.setFont('Helvetica', 10)
    c.drawCentredString(w / 2, y, titre_document)
    y -= 14
    c.setFont('Helvetica-Oblique', 8)
    c.drawCentredString(w / 2, y, f'Republique du {config.pays}')
    y -= 24

    c.setStrokeColorRGB(0.10, 0.24, 0.43)
    c.setLineWidth(1)
    c.line(marge, y, w - marge, y)
    y -= 22

    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont('Helvetica', 9)
    intro = (
        'Le present document atteste, a titre de preuve, l\'acceptation des textes legaux '
        'par l\'utilisateur identifie ci-dessous. Les enregistrements source sont immuables.'
    )
    for ligne in _couper_ligne(intro, 95):
        c.drawString(marge, y, ligne)
        y -= 12
    y -= 6

    c.setFont('Helvetica-Bold', 9)
    c.drawString(marge, y, f'Reference document : {reference}')
    y -= 20

    for idx, acc in enumerate(acceptations):
        if y < 120:
            c.showPage()
            y = h - 50
        user = acc.user
        date_j, heure = _formater_datetime(acc.date_acceptation)
        type_label = dict(TexteLegal.TYPE_CHOICES).get(acc.type_texte, acc.type_texte)
        contexte_label = dict(AcceptationTexteLegal.CONTEXTE_CHOICES).get(acc.contexte, acc.contexte)

        c.setFillColorRGB(0.10, 0.24, 0.43)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(marge, y, f'Acceptation {idx + 1} — {type_label}')
        y -= 16

        lignes = [
            ('Identifiant preuve', str(acc.uuid)),
            ('Utilisateur', user.email if user else '—'),
            ('Nom / etude', libelle_utilisateur(user) if user else '—'),
            ('Role', libelle_role(user) if user else '—'),
            ('Identifiant utilisateur', str(user.uuid) if user else '—'),
            ('Type de texte', type_label),
            ('Version acceptee', acc.version),
            ('Langue', acc.langue.upper()),
            ('Contexte', contexte_label),
            ('Date d\'acceptation', date_j),
            ('Heure d\'acceptation', heure),
            ('Adresse IP', acc.ip_address or '—'),
            ('Empreinte SHA-256 du texte', acc.hash_contenu),
        ]
        if acc.user_agent:
            lignes.append(('Navigateur / agent', acc.user_agent[:120]))

        c.setFillColorRGB(0.15, 0.15, 0.15)
        for label, valeur in lignes:
            c.setFont('Helvetica-Bold', 8)
            c.drawString(marge, y, f'{label} :')
            c.setFont('Helvetica', 8)
            for part in _couper_ligne(str(valeur), 78):
                c.drawString(marge + 155, y, part)
                y -= 11
            y -= 2
        y -= 12

    now = timezone.localtime()
    c.setFont('Helvetica-Oblique', 7)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    c.drawString(
        marge, 35,
        f'Document genere le {now.strftime("%d/%m/%Y")} a {now.strftime("%H:%M:%S")} — {config.nom_plateforme}',
    )
    c.save()
    return buffer.getvalue()


def _couper_ligne(texte: str, largeur: int) -> list[str]:
    mots = (texte or '').split()
    if not mots:
        return ['']
    lignes, courante = [], ''
    for mot in mots:
        test = f'{courante} {mot}'.strip()
        if len(test) <= largeur:
            courante = test
        else:
            if courante:
                lignes.append(courante)
            courante = mot
    if courante:
        lignes.append(courante)
    return lignes or ['']


def generer_pdf_preuve_acceptation(acceptation: AcceptationTexteLegal) -> bytes:
    type_label = dict(TexteLegal.TYPE_CHOICES).get(acceptation.type_texte, 'Texte legal')
    return _dessiner_preuve_pdf(
        [acceptation],
        f'ATTESTATION D\'ACCEPTATION — {type_label.upper()}',
        str(acceptation.uuid),
    )


def generer_pdf_dossier_utilisateur(user, acceptations=None) -> bytes:
    if acceptations is None:
        acceptations = list(
            AcceptationTexteLegal.objects.filter(user=user).select_related('user').order_by('date_acceptation')
        )
    return _dessiner_preuve_pdf(
        acceptations,
        'DOSSIER DE PREUVE — ACCEPTATIONS CGU ET CONFIDENTIALITE',
        str(user.uuid),
    )
