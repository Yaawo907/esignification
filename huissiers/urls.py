from django.urls import path
from . import views
app_name = 'huissiers'
urlpatterns = [
    path('', views.tableau_de_bord, name='tableau_de_bord'),
    path('rechercher/', views.rechercher_justiciable, name='rechercher'),
    path('significations/', views.liste_significations, name='significations'),
    path('inviter/', views.inviter_justiciable, name='inviter'),
]
