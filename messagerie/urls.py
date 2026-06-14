from django.urls import path
from . import views

app_name = 'messagerie'

urlpatterns = [
    path('', views.liste_conversations, name='liste_conversations'),
    path('nouvelle/', views.nouvelle_conversation, name='nouvelle_conversation'),
    path('<uuid:uuid>/', views.conversation, name='conversation'),
    path('<uuid:uuid>/envoyer/', views.envoyer_message, name='envoyer_message'),
    path('<uuid:uuid>/nouveaux/', views.nouveaux_messages_ajax, name='nouveaux_messages'),
    path('<uuid:uuid>/archiver/', views.archiver_conversation, name='archiver'),
    path('pj/<uuid:uuid>/', views.telecharger_piece_jointe, name='telecharger_pj'),
    path('non-lus/', views.compter_non_lus, name='non_lus'),
]
