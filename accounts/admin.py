from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, TokenActivation


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'role', 'is_active', 'is_staff', 'is_superuser', 'date_joined')
    list_filter = ('role', 'is_active', 'is_staff', 'is_superuser')
    search_fields = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profil', {'fields': ('role', 'uuid')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Sécurité 2FA', {'fields': ('mfa_active', 'mfa_methode', 'totp_secret')}),
        ('Dates', {'fields': ('last_login', 'date_joined', 'derniere_connexion')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'role', 'is_active', 'is_staff', 'is_superuser'),
        }),
    )
    readonly_fields = ('uuid', 'last_login', 'date_joined', 'derniere_connexion')


@admin.register(TokenActivation)
class TokenActivationAdmin(admin.ModelAdmin):
    list_display = ('email', 'type_token', 'utilise', 'date_creation', 'date_expiration')
    list_filter = ('type_token', 'utilise')
    search_fields = ('email', 'token')
    readonly_fields = ('uuid', 'token', 'date_creation')
