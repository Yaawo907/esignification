from django.urls import path
from . import views

app_name = 'huissiers'

urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),
    path('rechercher/', views.rechercher_justiciable, name='rechercher'),
    path('significations/', views.liste_significations, name='significations'),
    path('inviter/', views.inviter_justiciable, name='inviter'),
    path('inviter/<uuid:uuid>/renvoyer/', views.renvoyer_invitation_justiciable, name='renvoyer_invitation'),
    path('clercs/', views.liste_clercs, name='liste_clercs'),
    path('clercs/inviter/', views.inviter_clerc, name='inviter_clerc'),
    path('clercs/<uuid:uuid>/desactiver/', views.desactiver_clerc, name='desactiver_clerc'),
    path('demandes-modification/', views.liste_demandes_modification, name='liste_demandes_modification'),
    path('demandes-modification/<uuid:uuid>/', views.traiter_demande_modification, name='traiter_demande_modification'),
    path('profil/', views.profil_huissier, name='profil'),
    path('parametres/signatures/', views.parametres_signatures, name='parametres_signatures'),
]
