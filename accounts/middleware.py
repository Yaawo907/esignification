from django.shortcuts import redirect
from django.urls import reverse


class TextesLegauxMiddleware:
    """Redirige vers la réacceptation si les CGU ou la politique ont évolué."""

    PREFIXES_EXEMPTES = (
        '/connexion',
        '/deconnexion',
        '/verification',
        '/cgu',
        '/confidentialite',
        '/mentions-legales',
        '/reaccepter-textes-legaux',
        '/static/',
        '/media/',
        '/inscription/',
        '/confirmer-domicile',
        '/recuperation',
        '/reinitialiser-mdp',
        '/api/',
    )

    def __init__(self, get_response):
        self.get_response = get_response
        self._url_reacceptation = None

    def _url_reacceptation_courante(self):
        if self._url_reacceptation is None:
            self._url_reacceptation = reverse('accounts:reaccepter_textes_legaux')
        return self._url_reacceptation

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and getattr(user, 'role', None) != user.ADMIN:
            path = request.path
            if not any(path.startswith(prefix) for prefix in self.PREFIXES_EXEMPTES):
                from administration.textes_legaux_service import textes_a_reaccepter
                if textes_a_reaccepter(user) and path != self._url_reacceptation_courante():
                    return redirect('accounts:reaccepter_textes_legaux')
        return self.get_response(request)
