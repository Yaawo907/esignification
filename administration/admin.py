from django.contrib import admin
from .models import AcceptationTexteLegal, TexteLegal, PisteAudit


@admin.register(AcceptationTexteLegal)
class AcceptationTexteLegalAdmin(admin.ModelAdmin):
    list_display = ('user', 'type_texte', 'version', 'langue', 'contexte', 'date_acceptation', 'ip_address')
    list_filter = ('type_texte', 'contexte', 'langue')
    search_fields = ('user__email', 'version')
    readonly_fields = (
        'uuid', 'user', 'texte_legal', 'type_texte', 'version', 'langue',
        'hash_contenu', 'contexte', 'ip_address', 'user_agent', 'date_acceptation',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TexteLegal)
class TexteLegalAdmin(admin.ModelAdmin):
    list_display = ('titre', 'type_texte', 'langue', 'version', 'actif', 'date_mise_a_jour')
    list_filter = ('type_texte', 'langue', 'actif')

