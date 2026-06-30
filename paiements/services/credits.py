from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.utils import timezone

from administration.models import ConfigurationPlateforme
from huissiers.models import ProfilHuissier
from paiements.models import CommandeCredit, MouvementCredit
from significations.models import Signification

Q = Decimal('0.01')


class CreditInsuffisant(Exception):
    """Solde de crédits insuffisant pour envoyer une signification."""

    def __init__(self, solde: Decimal, requis: Decimal):
        self.solde = solde
        self.requis = requis
        super().__init__(f"Solde insuffisant : {solde} crédit(s), {requis} requis.")


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(Q, rounding=ROUND_HALF_UP)


def get_config_credits():
    return ConfigurationPlateforme.get()


def credit_debit_envoi() -> Decimal:
    """1 crédit débité à chaque envoi de signification."""
    return _quantize(Decimal(str(get_config_credits().credit_signification_reussie)))


def cout_net_apres_refus() -> Decimal:
    return _quantize(Decimal(str(get_config_credits().credit_signification_refusee)))


def cout_net_apres_annulation() -> Decimal:
    return _quantize(Decimal(str(get_config_credits().credit_signification_annulee)))


def prix_credit_fcfa() -> int:
    return int(get_config_credits().prix_credit_fcfa or 2000)


def get_solde(huissier: ProfilHuissier) -> Decimal:
    huissier.refresh_from_db(fields=['solde_credits'])
    return _quantize(Decimal(str(huissier.solde_credits)))


def peut_envoyer_signification(huissier: ProfilHuissier) -> bool:
    return get_solde(huissier) >= credit_debit_envoi()


def verifier_solde_envoi(huissier: ProfilHuissier):
    requis = credit_debit_envoi()
    solde = get_solde(huissier)
    if solde < requis:
        raise CreditInsuffisant(solde, requis)


def montant_remboursement_reponse(statut: str, debit: Decimal) -> Decimal:
    """
    Retour de crédit selon la réponse du justiciable (ou annulation).
    Acceptée → 0 remboursé. Refusée / annulée → différence avec le débit initial.
    """
    if statut == Signification.STATUT_ACCEPTEE:
        return Decimal('0')
    if statut == Signification.STATUT_REFUSEE:
        return _quantize(debit - cout_net_apres_refus())
    if statut in (
        Signification.STATUT_ANNULEE,
        Signification.STATUT_TRADITIONNELLE,
        Signification.STATUT_NON_DELIVREE,
    ):
        return _quantize(debit - cout_net_apres_annulation())
    return Decimal('0')


@transaction.atomic
def _appliquer_mouvement(
    huissier: ProfilHuissier,
    montant: Decimal,
    type_mouvement: str,
    description: str = '',
    signification=None,
    commande=None,
    auteur=None,
) -> MouvementCredit:
    huissier = ProfilHuissier.objects.select_for_update().get(pk=huissier.pk)
    nouveau_solde = _quantize(Decimal(str(huissier.solde_credits)) + montant)
    if nouveau_solde < 0:
        raise CreditInsuffisant(Decimal(str(huissier.solde_credits)), abs(montant))
    huissier.solde_credits = nouveau_solde
    huissier.save(update_fields=['solde_credits'])
    return MouvementCredit.objects.create(
        huissier=huissier,
        type_mouvement=type_mouvement,
        montant=montant,
        solde_apres=nouveau_solde,
        signification=signification,
        commande=commande,
        auteur=auteur,
        description=description,
    )


@transaction.atomic
def debiter_envoi_signification(signification: Signification, auteur=None) -> Optional[MouvementCredit]:
    """Débite 1 crédit à l'envoi de la signification."""
    if signification.credit_debite is not None:
        return None
    montant = credit_debit_envoi()
    mouvement = _appliquer_mouvement(
        signification.huissier,
        -montant,
        MouvementCredit.TYPE_CONSOMMATION,
        description=f"Débit signification {signification.reference}",
        signification=signification,
        auteur=auteur,
    )
    signification.credit_debite = montant
    signification.save(update_fields=['credit_debite'])
    return mouvement


@transaction.atomic
def rembourser_selon_reponse_client(signification: Signification, statut_reponse: str, auteur=None):
    """Rembourse le crédit selon la réponse du justiciable (acceptation, refus, annulation)."""
    if signification.credit_debite is None or signification.credit_ajuste:
        return
    debit = _quantize(Decimal(str(signification.credit_debite)))
    remboursement = montant_remboursement_reponse(statut_reponse, debit)
    if remboursement > 0:
        _appliquer_mouvement(
            signification.huissier,
            remboursement,
            MouvementCredit.TYPE_REMBOURSEMENT,
            description=f"Retour crédit {signification.reference} — {statut_reponse}",
            signification=signification,
            auteur=auteur,
        )
    signification.credit_ajuste = True
    signification.save(update_fields=['credit_ajuste'])


# Alias rétrocompatibilité
ajuster_credit_signification = rembourser_selon_reponse_client


@transaction.atomic
def attribuer_credits_gratuits(huissier: ProfilHuissier, nb_credits: Decimal, auteur, motif: str = ''):
    nb = _quantize(nb_credits)
    if nb <= 0:
        raise ValueError("Le montant doit être positif.")
    desc = motif or "Attribution gratuite par l'administrateur"
    return _appliquer_mouvement(
        huissier, nb, MouvementCredit.TYPE_GRATUIT, description=desc, auteur=auteur,
    )


@transaction.atomic
def finaliser_achat_credits(commande: CommandeCredit, transaction_id: str) -> CommandeCredit:
    if commande.statut == CommandeCredit.STATUT_COMPLETE:
        return commande
    commande = CommandeCredit.objects.select_for_update().get(pk=commande.pk)
    if commande.statut == CommandeCredit.STATUT_COMPLETE:
        return commande
    commande.statut = CommandeCredit.STATUT_COMPLETE
    commande.transaction_kkiapay = transaction_id
    commande.date_completion = timezone.now()
    commande.save(update_fields=['statut', 'transaction_kkiapay', 'date_completion'])
    _appliquer_mouvement(
        commande.huissier,
        commande.nb_credits,
        MouvementCredit.TYPE_ACHAT,
        description=f"Achat {commande.nb_credits} crédit(s) via Kkiapay",
        commande=commande,
    )
    return commande


@transaction.atomic
def creer_commande_credit(huissier: ProfilHuissier, nb_credits: Decimal) -> CommandeCredit:
    nb = _quantize(nb_credits)
    if nb <= 0:
        raise ValueError("Nombre de crédits invalide.")
    montant = int(nb * prix_credit_fcfa())
    commande = CommandeCredit.objects.create(
        huissier=huissier,
        nb_credits=nb,
        montant_fcfa=montant,
    )
    commande.reference_client = f"esignif_credit_{commande.uuid}_{montant}"
    commande.save(update_fields=['reference_client'])
    return commande
