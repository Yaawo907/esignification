from django.urls import path
from . import views
app_name = 'administration'
urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),
    path('huissiers/', views.liste_huissiers, name='liste_huissiers'),
    path('huissiers/creer/', views.creer_huissier, name='creer_huissier'),
    path('huissiers/<uuid:uuid>/statut/', views.changer_statut_huissier, name='statut_huissier'),
    path('configuration/', views.configuration, name='configuration'),
    path('textes-legaux/', views.gerer_textes_legaux, name='textes_legaux'),
    path('audit/', views.audit, name='audit'),
]
