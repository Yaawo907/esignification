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

    class Meta:
        verbose_name = 'Profil huissier'

    def __str__(self):
        return f"Me {self.nom} {self.prenom} — {self.nom_etude}"

    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"


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
