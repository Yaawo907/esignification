import uuid
from django.db import models


class ProfilAdmin(models.Model):
    """Profil de l'administrateur de la plateforme."""
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.OneToOneField(
        'accounts.User', on_delete=models.CASCADE, related_name='profil_admin',
    )
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100, blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profil administrateur'

    def __str__(self):
        return self.nom_complet or self.user.email

    @property
    def nom_complet(self):
        return f'{self.prenom} {self.nom}'.strip()

    @classmethod
    def get_for_user(cls, user):
        if not user or getattr(user, 'role', None) != 'admin':
            return None
        profil, _ = cls.objects.get_or_create(
            user=user,
            defaults={'nom': 'Administrateur', 'prenom': ''},
        )
        return profil


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

    # Logos officiels (pour les certificats PDF)
    logo_pays = models.ImageField(upload_to='logos/', null=True, blank=True,
                                  help_text='Logo/armoiries du pays (PNG/JPG, fond transparent recommandé)')
    logo_chambre = models.ImageField(upload_to='logos/', null=True, blank=True,
                                     help_text='Logo de la Chambre Nationale des Huissiers de Justice')

    # Certigna
    certigna_active = models.BooleanField(default=False)
    certigna_tsa_url = models.URLField(blank=True, default='https://tsa.certigna.fr/tsa')
    certigna_login = models.CharField(max_length=100, blank=True)
    certigna_password_chiffre = models.CharField(max_length=500, blank=True)
    certigna_oid = models.CharField(max_length=100, blank=True)
    certigna_heure_lot = models.TimeField(default='00:00')
    certigna_seuil_alerte_jetons = models.IntegerField(default=20)
    certigna_jetons_restants = models.IntegerField(default=0)

    # Yousign — signature électronique avancée (AES)
    yousign_active = models.BooleanField(default=False)
    yousign_mode = models.CharField(
        max_length=12, default='sandbox',
        choices=[('sandbox', 'Sandbox (test)'), ('production', 'Production')],
    )
    yousign_api_key_chiffre = models.CharField(max_length=500, blank=True,
        help_text='Clé API Yousign — chiffrée AES-256 en base')
    yousign_webhook_secret_chiffre = models.CharField(max_length=500, blank=True,
        help_text='Secret webhook Yousign pour valider les callbacks')

    # Kkiapay — paiement des crédits
    kkiapay_active = models.BooleanField(default=False)
    kkiapay_sandbox = models.BooleanField(default=True)
    kkiapay_public_key_chiffre = models.CharField(max_length=500, blank=True)
    kkiapay_private_key_chiffre = models.CharField(max_length=500, blank=True)
    kkiapay_secret_chiffre = models.CharField(max_length=500, blank=True)

    # Tarification crédits : 1 crédit débité à l'envoi, remboursement partiel selon la réponse
    prix_credit_fcfa = models.PositiveIntegerField(
        default=2000, help_text='Prix d\'achat d\'un crédit en FCFA',
    )
    credit_signification_reussie = models.DecimalField(
        max_digits=6, decimal_places=2, default=1,
        help_text='Crédit débité à l\'envoi (et conservé si le justiciable accepte)',
    )
    credit_signification_refusee = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.5,
        help_text='Coût net si le justiciable refuse (remboursement = débit − ce montant)',
    )
    credit_signification_annulee = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.25,
        help_text='Coût net si annulation (remboursement = débit − ce montant)',
    )

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


class AcceptationTexteLegal(models.Model):
    """Preuve immuable de l'acceptation des CGU et de la politique de confidentialité."""

    CONTEXTE_INSCRIPTION_HUISSIER = 'inscription_huissier'
    CONTEXTE_INSCRIPTION_JUSTICIABLE = 'inscription_justiciable'
    CONTEXTE_INSCRIPTION_CLERC = 'inscription_clerc'
    CONTEXTE_REACCEPTATION = 'reacceptation_connexion'
    CONTEXTE_CHOICES = [
        (CONTEXTE_INSCRIPTION_HUISSIER, 'Inscription huissier'),
        (CONTEXTE_INSCRIPTION_JUSTICIABLE, 'Inscription justiciable'),
        (CONTEXTE_INSCRIPTION_CLERC, 'Inscription clerc'),
        (CONTEXTE_REACCEPTATION, 'Réacceptation à la connexion'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    user = models.ForeignKey(
        'accounts.User', on_delete=models.CASCADE, related_name='acceptations_textes_legaux',
    )
    texte_legal = models.ForeignKey(
        TexteLegal, on_delete=models.PROTECT, null=True, blank=True, related_name='acceptations',
    )
    type_texte = models.CharField(max_length=20, choices=TexteLegal.TYPE_CHOICES)
    version = models.CharField(max_length=20)
    langue = models.CharField(max_length=5)
    hash_contenu = models.CharField(max_length=64, help_text='Empreinte SHA-256 du contenu accepté')
    contexte = models.CharField(max_length=30, choices=CONTEXTE_CHOICES)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    date_acceptation = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Acceptation de texte légal'
        verbose_name_plural = 'Acceptations de textes légaux'
        ordering = ['-date_acceptation']
        indexes = [
            models.Index(fields=['user', 'type_texte', '-date_acceptation']),
        ]

    def __str__(self):
        return f"{self.user.email} — {self.type_texte} v{self.version} — {self.date_acceptation:%d/%m/%Y %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk and AcceptationTexteLegal.objects.filter(pk=self.pk).exists():
            return
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass


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
        verbose_name = "Piste d'audit"
        ordering = ['-date']

    def __str__(self):
        return f"{self.action} — {self.user_email} — {self.date}"

    def save(self, *args, **kwargs):
        if self.pk and PisteAudit.objects.filter(pk=self.pk).exists():
            return  # Immuable
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Suppression interdite
