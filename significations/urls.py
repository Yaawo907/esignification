from django.urls import path
from . import views
app_name = 'significations'
urlpatterns = [
    path('envoyer/', views.envoyer_signification, name='envoyer'),
    path('repondre/<uuid:uuid>/', views.repondre_signification, name='repondre'),
    path('acte/<uuid:uuid>/telecharger/', views.telecharger_acte, name='telecharger_acte'),
    path('certificat/<uuid:uuid>/telecharger/', views.telecharger_certificat, name='telecharger_certificat'),
    path('<uuid:uuid>/reponse/', views.voir_reponse, name='voir_reponse'),
    path('<uuid:uuid>/reponse/telecharger/', views.telecharger_reponse, name='telecharger_reponse'),
    path('<uuid:uuid>/traditionnel/', views.basculer_traditionnel, name='basculer_traditionnel'),
    path('<uuid:uuid>/constat/', views.telecharger_constat, name='telecharger_constat'),
    path('webhook/yousign/', views.webhook_yousign, name='webhook_yousign'),
]
