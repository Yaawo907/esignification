def config_plateforme(request):
    try:
        from administration.models import ConfigurationPlateforme
        config = ConfigurationPlateforme.get()
        return {'config': config}
    except Exception:
        return {'config': None}
