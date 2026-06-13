import uuid
from django.db import models


class ConfigurationPlateforme(models.Model):
    """Singleton — une seule ligne en base"""
    nom_plateforme = models.CharField(max_length=100, default='e-Signification Bénin')
    pays = models.CharField(max_length=100, default='Bénin')
    langue_defaut = models.CharField(max_length=5, default='fr', choices=[('fr','Français'),('en','English'),('es','Español')])
    article_loi_signification = models.TextField(blank=True)
    decret_reference = models.TextField(blank=True)
    nom_autorite_tutelle = models.CharField(max_length=200, blank=True)
    delai_relance_1_jours = models.IntegerField(default=3)
    delai_relance_2_jours = models.IntegerField(default=6)
    methode_2fa_defaut = models.CharField(max_length=10, default='email', choices=[('email','Email'),('otp','SMS OTP'),('totp','Authenticator')])
    copyright_texte = models.CharField(max_length=200, default='© e-Signification Bénin')
    email_contact = models.EmailField(blank=True)
    telephone_contact = models.CharField(max_length=20, blank=True)
    adresse_contact = models.TextField(blank=True)

    # Certigna
    certigna_active = models.BooleanField(default=False)
    certigna_tsa_url = models.URLField(blank=True, default='https://tsa.certigna.fr/tsa')
    certigna_login = models.CharField(max_length=100, blank=True)
    certigna_password_chiffre = models.CharField(max_length=500, blank=True)
    certigna_oid = models.CharField(max_length=100, blank=True)
    certigna_heure_lot = models.TimeField(default='00:00')
    certigna_seuil_alerte_jetons = models.IntegerField(default=20)
    certigna_jetons_restants = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Configuration plateforme'

    def __str__(self):
        return f"Configuration — {self.nom_plateforme}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class TexteLegal(models.Model):
    TYPE_CGU = 'cgu'
    TYPE_MENTIONS = 'mentions'
    TYPE_CONFIDENTIALITE = 'confidentialite'
    TYPE_CHOICES = [
        (TYPE_CGU, 'Conditions Générales d\'Utilisation'),
        (TYPE_MENTIONS, 'Mentions légales'),
        (TYPE_CONFIDENTIALITE, 'Politique de confidentialité'),
    ]
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    type_texte = models.CharField(max_length=20, choices=TYPE_CHOICES)
    langue = models.CharField(max_length=5, choices=[('fr','Français'),('en','English'),('es','Español')])
    titre = models.CharField(max_length=200)
    contenu_html = models.TextField()
    version = models.CharField(max_length=20, default='1.0')
    date_mise_a_jour = models.DateTimeField(auto_now=True)
    actif = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Texte légal'
        unique_together = ['type_texte', 'langue']

    def __str__(self):
        return f"{self.get_type_texte_display()} ({self.langue})"


class ModeleEmail(models.Model):
    TYPE_CHOICES = [
        ('activation_huissier', 'Activation compte huissier'),
        ('invitation_justiciable', 'Invitation justiciable'),
        ('confirmation_domicile', 'Confirmation domicile électronique'),
        ('signification_envoyee', 'Signification envoyée'),
        ('relance_1', 'Relance 1'),
        ('relance_2', 'Relance 2'),
        ('reponse_recue', 'Réponse reçue'),
        ('certificat_genere', 'Certificat généré'),
        ('recuperation_mdp', 'Récupération mot de passe'),
        ('alerte_jetons', 'Alerte jetons Certigna'),
    ]
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    type_email = models.CharField(max_length=50, choices=TYPE_CHOICES)
    langue = models.CharField(max_length=5, choices=[('fr','Français'),('en','English'),('es','Español')])
    sujet = models.CharField(max_length=200)
    corps_html = models.TextField()
    actif = models.BooleanField(default=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Modèle d\'email'
        unique_together = ['type_email', 'langue']

    def __str__(self):
        return f"{self.get_type_email_display()} ({self.langue})"


class LotMerkle(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    date_lot = models.DateField(unique=True)
    hash_racine = models.CharField(max_length=64)
    jeton_certigna = models.BinaryField(null=True, blank=True)
    nb_actes_couverts = models.IntegerField(default=0)
    date_creation = models.DateTimeField(auto_now_add=True)
    statut = models.CharField(max_length=20, default='en_attente', choices=[
        ('en_attente', 'En attente'),
        ('certifie', 'Certifié par Certigna'),
        ('local', 'Horodatage local uniquement'),
    ])

    class Meta:
        verbose_name = 'Lot Merkle'
        ordering = ['-date_lot']

    def __str__(self):
        return f"Lot Merkle {self.date_lot} — {self.nb_actes_couverts} actes"


class PisteAudit(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True)
    user_email = models.EmailField(blank=True)
    action = models.CharField(max_length=100)
    objet_type = models.CharField(max_length=50, blank=True)
    objet_uuid = models.CharField(max_length=36, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Piste d\'audit'
        ordering = ['-date']
        # Lecture seule — pas de modification ni suppression

    def __str__(self):
        return f"{self.action} — {self.user_email} — {self.date}"

    def save(self, *args, **kwargs):
        if self.pk and PisteAudit.objects.filter(pk=self.pk).exists():
            return  # Immuable
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Suppression interdite
