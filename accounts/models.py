import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("L'email est obligatoire")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ADMIN = 'admin'
    HUISSIER = 'huissier'
    CLERC = 'clerc'
    JUSTICIABLE = 'justiciable'

    ROLE_CHOICES = [
        (ADMIN, 'Administrateur'),
        (HUISSIER, 'Huissier de justice'),
        (CLERC, 'Clerc assermenté'),
        (JUSTICIABLE, 'Justiciable'),
    ]

    MFA_EMAIL = 'email'
    MFA_OTP = 'otp'
    MFA_TOTP = 'totp'
    MFA_CHOICES = [
        (MFA_EMAIL, 'Code par email'),
        (MFA_OTP, 'Code SMS (OTP)'),
        (MFA_TOTP, 'Application authentificateur (TOTP)'),
    ]

    # Identifiants
    id = models.BigAutoField(primary_key=True)
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    email = models.EmailField(unique=True, verbose_name="Email")

    # Infos de base
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=JUSTICIABLE)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    derniere_connexion = models.DateTimeField(null=True, blank=True)

    # Sécurité 2FA
    mfa_methode = models.CharField(max_length=10, choices=MFA_CHOICES, default=MFA_EMAIL)
    mfa_active = models.BooleanField(default=True)
    totp_secret = models.CharField(max_length=32, blank=True)

    # Code MFA temporaire (email/SMS)
    mfa_code = models.CharField(max_length=6, blank=True)
    mfa_code_expiry = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'

    def __str__(self):
        return self.email

    @property
    def is_admin(self):
        return self.role == self.ADMIN

    @property
    def is_huissier(self):
        return self.role in [self.HUISSIER, self.CLERC]

    @property
    def is_justiciable(self):
        return self.role == self.JUSTICIABLE

    def get_profil(self):
        if self.role in [self.HUISSIER, self.CLERC]:
            return getattr(self, 'profil_huissier', None)
        elif self.role == self.JUSTICIABLE:
            return getattr(self, 'profil_justiciable', None)
        return None


class TokenActivation(models.Model):
    """Tokens pour activation, invitation, récupération de mot de passe"""
    ACTIVATION_HUISSIER = 'activation_huissier'
    INVITATION_JUSTICIABLE = 'invitation_justiciable'
    RECUPERATION_MDP = 'recuperation_mdp'
    CONFIRMATION_EMAIL = 'confirmation_email'
    MFA_CODE = 'mfa_code'
    CHANGEMENT_EMAIL_DOMICILE = 'changement_email_domicile'
    ACTIVATION_CLERC = 'activation_clerc'

    TYPE_CHOICES = [
        (ACTIVATION_HUISSIER, 'Activation huissier'),
        (INVITATION_JUSTICIABLE, 'Invitation justiciable'),
        (RECUPERATION_MDP, 'Récupération mot de passe'),
        (CONFIRMATION_EMAIL, 'Confirmation email'),
        (MFA_CODE, 'Code MFA'),
        (CHANGEMENT_EMAIL_DOMICILE, 'Changement email domicile'),
        (ACTIVATION_CLERC, 'Activation clerc'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, primary_key=True)
    token = models.CharField(max_length=255, unique=True, db_index=True)
    type_token = models.CharField(max_length=30, choices=TYPE_CHOICES)
    email = models.EmailField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    utilise = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_expiration = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Token d\'activation'
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.type_token} — {self.email}"

    @property
    def est_expire(self):
        return timezone.now() > self.date_expiration

    @property
    def est_valide(self):
        return not self.utilise and not self.est_expire
