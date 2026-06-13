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
