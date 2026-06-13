from django.urls import path
from . import views
app_name = 'significations'
urlpatterns = [
    path('envoyer/', views.envoyer_signification, name='envoyer'),
    path('repondre/<uuid:uuid>/', views.repondre_signification, name='repondre'),
    path('acte/<uuid:uuid>/telecharger/', views.telecharger_acte, name='telecharger_acte'),
    path('certificat/<uuid:uuid>/telecharger/', views.telecharger_certificat, name='telecharger_certificat'),
]
