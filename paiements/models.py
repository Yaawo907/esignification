import uuid
from decimal import Decimal
from django.db import models


class CommandeCredit(models.Model):
    """Commande d'achat de crédits via Kkiapay."""

    STATUT_EN_ATTENTE = 'en_attente'
    STATUT_COMPLETE = 'complete'
    STATUT_ECHOUE = 'echoue'
    STATUT_CHOICES = [
        (STATUT_EN_ATTENTE, 'En attente'),
        (STATUT_COMPLETE, 'Complétée'),
        (STATUT_ECHOUE, 'Échouée'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    huissier = models.ForeignKey(
        'huissiers.ProfilHuissier', on_delete=models.PROTECT, related_name='commandes_credits',
    )
    nb_credits = models.DecimalField(max_digits=10, decimal_places=2)
    montant_fcfa = models.PositiveIntegerField()
    transaction_kkiapay = models.CharField(max_length=120, blank=True, db_index=True)
    statut = models.CharField(max_length=20, choices=STATUT_CHOICES, default=STATUT_EN_ATTENTE)
    reference_client = models.CharField(max_length=200, blank=True, db_index=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_completion = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Commande de crédits'
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.nb_credits} crédit(s) — {self.huissier} — {self.get_statut_display()}"


class MouvementCredit(models.Model):
    """Historique immuable des mouvements de crédits."""

    TYPE_ACHAT = 'achat'
    TYPE_GRATUIT = 'gratuit'
    TYPE_CONSOMMATION = 'consommation'
    TYPE_REMBOURSEMENT = 'remboursement'
    TYPE_AJUSTEMENT = 'ajustement'
    TYPE_CHOICES = [
        (TYPE_ACHAT, 'Achat'),
        (TYPE_GRATUIT, 'Attribution gratuite'),
        (TYPE_CONSOMMATION, 'Débit signification'),
        (TYPE_REMBOURSEMENT, 'Retour crédit (réponse client)'),
        (TYPE_AJUSTEMENT, 'Ajustement'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    huissier = models.ForeignKey(
        'huissiers.ProfilHuissier', on_delete=models.PROTECT, related_name='mouvements_credits',
    )
    type_mouvement = models.CharField(max_length=20, choices=TYPE_CHOICES)
    montant = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text='Positif = crédit ajouté, négatif = crédit consommé',
    )
    solde_apres = models.DecimalField(max_digits=12, decimal_places=2)
    signification = models.ForeignKey(
        'significations.Signification', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mouvements_credits',
    )
    commande = models.ForeignKey(
        CommandeCredit, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='mouvements',
    )
    auteur = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL, null=True, blank=True,
    )
    description = models.CharField(max_length=300, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Mouvement de crédit'
        ordering = ['-date']

    def __str__(self):
        return f"{self.get_type_mouvement_display()} {self.montant} — {self.huissier}"
