from django.urls import path
from . import views
app_name = 'administration'
urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),
    path('huissiers/', views.liste_huissiers, name='liste_huissiers'),
    path('huissiers/creer/', views.creer_huissier, name='creer_huissier'),
    path('huissiers/<uuid:uuid>/statut/', views.changer_statut_huissier, name='statut_huissier'),
    path('huissiers/<uuid:uuid>/renvoyer-invitation/', views.renvoyer_invitation_huissier, name='renvoyer_invitation'),
    path('huissiers/invitation/<uuid:uuid>/renvoyer/', views.renvoyer_invitation_token_huissier, name='renvoyer_invitation_token'),
    path('huissiers/invitation/<uuid:uuid>/supprimer/', views.supprimer_invitation_huissier, name='supprimer_invitation'),
    path('configuration/', views.configuration, name='configuration'),
    path('profil/', views.profil, name='profil'),
    path('textes-legaux/', views.gerer_textes_legaux, name='textes_legaux'),
    path('audit/', views.audit, name='audit'),
    path('acceptations-textes-legaux/', views.acceptations_textes_legaux, name='acceptations_textes_legaux'),
    path(
        'acceptations-textes-legaux/<uuid:uuid>/preuve.pdf',
        views.preuve_acceptation_pdf,
        name='preuve_acceptation_pdf',
    ),
    path(
        'acceptations-textes-legaux/utilisateur/<uuid:user_uuid>/preuve.pdf',
        views.preuve_acceptations_utilisateur_pdf,
        name='preuve_acceptations_utilisateur_pdf',
    ),
    path('paiements-credits/', views.gestion_paiements_credits, name='paiements_credits'),
    path('yousign/tester/', views.tester_yousign, name='tester_yousign'),
]
