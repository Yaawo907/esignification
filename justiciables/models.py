import uuid
from django.db import models
from accounts.models import User


class ProfilJusticiable(models.Model):
    TYPE_PARTICULIER = 'particulier'
    TYPE_ENTREPRISE = 'entreprise'
    TYPE_CHOICES = [
        (TYPE_PARTICULIER, 'Particulier'),
        (TYPE_ENTREPRISE, 'Entreprise'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_justiciable')
    type_compte = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_PARTICULIER)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)
    nom_entreprise = models.CharField(max_length=200, blank=True)
    ifu = models.CharField(max_length=50, blank=True, verbose_name="Numéro IFU")
    npi = models.CharField(max_length=50, blank=True, verbose_name="Numéro NPI")
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email_domicile = models.EmailField(verbose_name="Email d'élection de domicile électronique")
    email_domicile_verifie = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profil justiciable'

    def __str__(self):
        if self.type_compte == self.TYPE_ENTREPRISE:
            return self.nom_entreprise
        return f"{self.prenom} {self.nom}"

    @property
    def nom_complet(self):
        if self.type_compte == self.TYPE_ENTREPRISE:
            return self.nom_entreprise
        return f"{self.prenom} {self.nom}"


class DemandeModificationProfil(models.Model):
    """Demande de modification des infos personnelles d'un justiciable, soumise à un huissier."""
    STATUT_EN_ATTENTE = 'en_attente'
    STATUT_VALIDEE    = 'validee'
    STATUT_REFUSEE    = 'refusee'
    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE, 'En attente'),
        (STATUT_VALIDEE,    'Validée'),
        (STATUT_REFUSEE,    'Refusée'),
    ]

    uuid          = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    justiciable   = models.ForeignKey(ProfilJusticiable, on_delete=models.CASCADE,
                                      related_name='demandes_modification')
    huissier      = models.ForeignKey('huissiers.ProfilHuissier', on_delete=models.SET_NULL,
                                      null=True, related_name='demandes_modification_justiciables')
    statut        = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE)

    # Nouvelles valeurs demandées (vides = pas de changement souhaité)
    nouveau_nom         = models.CharField(max_length=100, blank=True)
    nouveau_prenom      = models.CharField(max_length=100, blank=True)
    nouveau_nom_entreprise = models.CharField(max_length=200, blank=True)
    nouveau_telephone   = models.CharField(max_length=20, blank=True)
    nouvelle_adresse    = models.TextField(blank=True)
    nouveau_ifu         = models.CharField(max_length=50, blank=True)
    nouveau_npi         = models.CharField(max_length=50, blank=True)
    message_justiciable = models.TextField(blank=True, verbose_name="Message / motif de la demande")

    # Pièces justificatives (chiffrées)
    piece_1_chiffree    = models.BinaryField(null=True, blank=True)
    piece_1_nom         = models.CharField(max_length=255, blank=True)
    piece_2_chiffree    = models.BinaryField(null=True, blank=True)
    piece_2_nom         = models.CharField(max_length=255, blank=True)

    # Réponse de l'huissier
    motif_refus   = models.TextField(blank=True)
    date_traitement = models.DateTimeField(null=True, blank=True)

    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Demande de modification de profil'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Demande {self.uuid} — {self.justiciable} ({self.statut})"


class InvitationJusticiable(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    huissier = models.ForeignKey('huissiers.ProfilHuissier', on_delete=models.CASCADE, related_name='invitations_envoyees')
    email_cible = models.EmailField()
    token = models.CharField(max_length=255, unique=True)
    utilise = models.BooleanField(default=False)
    justiciable_cree = models.ForeignKey(ProfilJusticiable, on_delete=models.SET_NULL, null=True, blank=True)
    date_envoi = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateTimeField()

    class Meta:
        verbose_name = 'Invitation justiciable'
        ordering = ['-date_envoi']

    def __str__(self):
        return f"Invitation → {self.email_cible} par {self.huissier}"
