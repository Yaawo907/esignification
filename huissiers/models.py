import uuid
from django.db import models
from accounts.models import User


class ProfilHuissier(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_huissier')
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    nom_etude = models.CharField(max_length=200)
    ifu = models.CharField(max_length=50, blank=True, verbose_name="Numéro IFU")
    npi = models.CharField(max_length=50, blank=True, verbose_name="Numéro NPI")
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    statut = models.CharField(max_length=20, choices=[
        ('actif', 'Actif'),
        ('inactif', 'Inactif'),
        ('en_attente', 'En attente d\'activation'),
    ], default='en_attente')
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)
    solde_credits = models.DecimalField(
        max_digits=12, decimal_places=2, default=0,
        help_text='Solde de crédits disponibles pour les significations',
    )

    class Meta:
        verbose_name = 'Profil huissier'

    def __str__(self):
        return f"Me {self.nom} {self.prenom} — {self.nom_etude}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"


class ParametreSignatureHuissier(models.Model):
    """Stocke les 3 tampons/signatures visuels de l'huissier (base64 PNG)."""
    huissier = models.OneToOneField(
        ProfilHuissier, on_delete=models.CASCADE,
        related_name='parametres_signature'
    )
    # Signature manuscrite seule
    signature_simple_b64 = models.TextField(blank=True)
    signature_simple_label = models.CharField(max_length=80, default='Signature simple')
    # Signature + cachet de l'étude
    signature_cachet_b64 = models.TextField(blank=True)
    signature_cachet_label = models.CharField(max_length=80, default='Signature avec cachet')
    # Cachet seul (tampon de l'étude)
    cachet_simple_b64 = models.TextField(blank=True)
    cachet_simple_label = models.CharField(max_length=80, default='Cachet simple')

    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Paramètres signature huissier'

    def __str__(self):
        return f"Signatures — {self.huissier}"


class ProfilClerc(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil_clerc')
    huissier = models.ForeignKey(ProfilHuissier, on_delete=models.CASCADE, related_name='clercs')
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    telephone = models.CharField(max_length=20, blank=True)
    actif = models.BooleanField(default=True)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Clerc assermenté'

    def __str__(self):
        return f"{self.prenom} {self.nom} (clerc de Me {self.huissier.nom})"
