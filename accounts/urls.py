from django.urls import path
from . import views

app_name = 'accounts'
urlpatterns = [
    path('connexion/', views.connexion, name='connexion'),
    path('verification/', views.mfa_verification, name='mfa_verification'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('inscription/huissier/', views.inscription_huissier, name='inscription_huissier'),
    path('inscription/justiciable/', views.inscription_justiciable, name='inscription_justiciable'),
    path('confirmer-domicile/', views.confirmer_domicile, name='confirmer_domicile'),
    path('modifier-mdp/', views.modifier_mot_de_passe, name='modifier_mdp'),
    path('recuperation/', views.recuperation_compte, name='recuperation_compte'),
    path('reinitialiser-mdp/', views.reinitialiser_mdp, name='reinitialiser_mdp'),
]
