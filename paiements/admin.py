from django.contrib import admin
from .models import CommandeCredit, MouvementCredit


@admin.register(CommandeCredit)
class CommandeCreditAdmin(admin.ModelAdmin):
    list_display = ('uuid', 'huissier', 'nb_credits', 'montant_fcfa', 'statut', 'date_creation')
    list_filter = ('statut',)
    search_fields = ('huissier__nom', 'transaction_kkiapay', 'reference_client')
    readonly_fields = ('uuid', 'date_creation', 'date_completion')


@admin.register(MouvementCredit)
class MouvementCreditAdmin(admin.ModelAdmin):
    list_display = ('date', 'huissier', 'type_mouvement', 'montant', 'solde_apres')
    list_filter = ('type_mouvement',)
    readonly_fields = ('uuid', 'date', 'solde_apres')
