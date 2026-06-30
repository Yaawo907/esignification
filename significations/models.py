import uuid
from django.db import models
from django.utils import timezone
from accounts.models import User


class Signification(models.Model):
    STATUT_EN_ATTENTE = 'en_attente'
    STATUT_ATTENTE_SIGNATURE = 'attente_signature'   # Yousign : en attente de signature huissier
    STATUT_ACCEPTEE = 'acceptee'
    STATUT_REFUSEE = 'refusee'
    STATUT_RELANCE_1 = 'relance_1'
    STATUT_RELANCE_2 = 'relance_2'
    STATUT_NON_DELIVREE = 'non_delivree'
    STATUT_TRADITIONNELLE = 'traditionnelle'
    STATUT_REPONDU = 'repondu'
    STATUT_ANNULEE = 'annulee'

    STATUT_CHOICES = [
        (STATUT_ATTENTE_SIGNATURE, 'En attente de signature huissier'),
        (STATUT_EN_ATTENTE, 'En attente'),
        (STATUT_ACCEPTEE, 'Acceptée'),
        (STATUT_REFUSEE, 'Refusée'),
        (STATUT_RELANCE_1, 'Relance 1'),
        (STATUT_RELANCE_2, 'Relance 2'),
        (STATUT_NON_DELIVREE, 'Non délivrée électroniquement'),
        (STATUT_TRADITIONNELLE, 'Bascule signification traditionnelle'),
        (STATUT_REPONDU, 'Réponse reçue'),
        (STATUT_ANNULEE, 'Annulée'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    reference = models.CharField(max_length=50, unique=True)
    huissier = models.ForeignKey('huissiers.ProfilHuissier', on_delete=models.PROTECT, related_name='significations')
    expediteur = models.ForeignKey(User, on_delete=models.PROTECT, related_name='significations_envoyees')
    justiciable = models.ForeignKey('justiciables.ProfilJusticiable', on_delete=models.PROTECT, related_name='significations_recues')

    # Fichier acte (chiffré)
    fichier_chiffre = models.BinaryField(null=True, blank=True)
    nom_fichier_original = models.CharField(max_length=255, blank=True)
    titre_acte = models.CharField(max_length=300, blank=True, verbose_name="Titre de l'acte")
    taille_fichier = models.IntegerField(default=0)

    # Options
    necessite_reponse = models.BooleanField(default=False)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE)

    # Dates
    date_envoi = models.DateTimeField(auto_now_add=True)
    date_acceptation = models.DateTimeField(null=True, blank=True)
    date_refus = models.DateTimeField(null=True, blank=True)
    date_horodatage_envoi = models.DateTimeField(null=True, blank=True)

    # Horodatage
    hash_acte = models.CharField(max_length=64, blank=True)
    hash_merkle_position = models.IntegerField(null=True, blank=True)

    # Signature visuelle de l'huissier (PNG base64)
    signature_huissier_b64 = models.TextField(blank=True)

    # Motif refus
    motif_refus = models.TextField(blank=True)

    # Yousign — signature électronique avancée (optionnel selon config admin)
    yousign_signature_request_id = models.CharField(max_length=100, blank=True, db_index=True,
        help_text='ID de la demande de signature Yousign')
    yousign_statut = models.CharField(max_length=30, blank=True,
        help_text='Statut Yousign : pending, ongoing, done, rejected, expired, canceled')
    yousign_signer_id = models.CharField(max_length=100, blank=True,
        help_text='ID du signataire Yousign (huissier)')
    yousign_audit_trail_chiffre = models.BinaryField(null=True, blank=True,
        help_text='Dossier de preuve Yousign (audit trail PDF chiffré)')

    # Crédits — débit à l'envoi, ajustement selon issue finale
    credit_debite = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    credit_ajuste = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Signification'
        ordering = ['-date_envoi']

    def __str__(self):
        return f"{self.reference} — {self.justiciable}"

    def save(self, *args, **kwargs):
        if not self.reference:
            from django.utils import timezone as tz
            year = tz.now().year
            count = Signification.objects.filter(date_envoi__year=year).count() + 1
            self.reference = f"SIG-{year}-{count:04d}"
        super().save(*args, **kwargs)


class CertificatSignification(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    signification = models.OneToOneField(Signification, on_delete=models.PROTECT, related_name='certificat')
    date_reception = models.DateTimeField()
    timezone_reception = models.CharField(max_length=50, default='Africa/Porto-Novo')
    hash_certificat = models.CharField(max_length=64)
    hash_merkle = models.CharField(max_length=64, blank=True)
    chemin_merkle = models.JSONField(default=list, blank=True)
    horodatage_certigna = models.BinaryField(null=True, blank=True)
    lot_merkle = models.ForeignKey('administration.LotMerkle', on_delete=models.SET_NULL, null=True, blank=True)
    fichier_certificat_chiffre = models.BinaryField(null=True, blank=True)
    date_generation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Certificat de signification'

    def __str__(self):
        return f"Certificat {self.signification.reference}"


class ReponseJusticiable(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    signification = models.OneToOneField(Signification, on_delete=models.PROTECT, related_name='reponse')
    texte_reponse = models.TextField(blank=True, verbose_name="Texte de la réponse")
    fichier_reponse_chiffre = models.BinaryField(null=True, blank=True)
    nom_fichier_reponse = models.CharField(max_length=255, blank=True)
    date_envoi_justiciable = models.DateTimeField(auto_now_add=True)
    date_reception_huissier = models.DateTimeField(null=True, blank=True)
    hash_contenu = models.CharField(max_length=64, blank=True)
    hash_reponse = models.CharField(max_length=64, blank=True)
    nom_fichier_annexe = models.CharField(max_length=255, blank=True)
    hash_annexe = models.CharField(max_length=64, blank=True)
    hash_merkle = models.CharField(max_length=64, blank=True)
    chemin_merkle = models.JSONField(default=list, blank=True)
    horodatage_certigna = models.BinaryField(null=True, blank=True)
    lot_merkle = models.ForeignKey(
        'administration.LotMerkle', on_delete=models.SET_NULL, null=True, blank=True,
    )
    vue_par_huissier = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Réponse justiciable'

    def __str__(self):
        return f"Réponse — {self.signification.reference}"

    def enregistrer_texte(self, texte_clair: str) -> None:
        from securite.chiffrement import chiffrer_texte
        self.texte_reponse = chiffrer_texte(texte_clair) if texte_clair else ''

    @property
    def texte_clair(self) -> str:
        if not self.texte_reponse:
            return ''
        from securite.chiffrement import dechiffrer_texte
        try:
            return dechiffrer_texte(self.texte_reponse)
        except Exception:
            from html import unescape
            return unescape(self.texte_reponse)


class RelanceSignification(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    signification = models.ForeignKey(Signification, on_delete=models.CASCADE, related_name='relances')
    numero_relance = models.IntegerField(choices=[(1, 'Relance 1'), (2, 'Relance 2')])
    date_envoi = models.DateTimeField(auto_now_add=True)
    constat_chiffre = models.BinaryField(null=True, blank=True)

    class Meta:
        verbose_name = 'Relance'
        unique_together = ['signification', 'numero_relance']

    def __str__(self):
        return f"Relance {self.numero_relance} — {self.signification.reference}"
