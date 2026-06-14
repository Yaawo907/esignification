from django.urls import path
from . import views
app_name = 'justiciables'
urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),
    path('significations/', views.liste_significations, name='significations'),
    path('reponse/<uuid:uuid>/', views.envoyer_reponse, name='envoyer_reponse'),
    path('profil/', views.profil, name='profil'),
    path('confirmer-email/', views.confirmer_changement_email, name='confirmer_email'),
    path('profil/modifier/', views.demander_modification_profil, name='demander_modification'),
]
