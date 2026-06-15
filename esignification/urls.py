from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.views.i18n import set_language
from django.shortcuts import redirect


def home(request):
    from accounts.models import User
    from django.shortcuts import render as _render
    if request.user.is_authenticated:
        if request.user.role == User.ADMIN:
            return redirect('/administration/')
        elif request.user.role in [User.HUISSIER, User.CLERC]:
            return redirect('/huissier/')
        elif request.user.role == User.JUSTICIABLE:
            return redirect('/justiciable/')
    return _render(request, 'landing.html')


urlpatterns = [
    path('', home, name='home'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('set-language/', set_language, name='set_language'),
    # Apps
    path('', include('accounts.urls', namespace='accounts')),
    path('huissier/', include('huissiers.urls', namespace='huissiers')),
    path('justiciable/', include('justiciables.urls', namespace='justiciables')),
    path('administration/', include('administration.urls', namespace='administration')),
    path('significations/', include('significations.urls', namespace='significations')),
    path('api/', include('api.urls', namespace='api')),
    path('messagerie/', include('messagerie.urls', namespace='messagerie')),
]

# Fichiers media — servis par Django (DEBUG=True ou False)
# En production sur un vrai serveur, déléguer à Nginx à la place
urlpatterns += [
    re_path(r'^media/(?P<path>.+)$', serve, {'document_root': settings.MEDIA_ROOT}),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
