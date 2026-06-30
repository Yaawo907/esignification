def config_plateforme(request):
    try:
        from administration.models import ConfigurationPlateforme
        config = ConfigurationPlateforme.get()
        return {'config': config}
    except Exception:
        return {'config': None}


def profil_admin(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {}
    if getattr(request.user, 'role', None) != 'admin':
        return {}
    try:
        from administration.models import ProfilAdmin
        return {'profil_admin': ProfilAdmin.get_for_user(request.user)}
    except Exception:
        return {}
