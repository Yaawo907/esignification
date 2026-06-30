from django.urls import path
from . import views

app_name = 'paiements'

urlpatterns = [
    path('credits/', views.achat_credits, name='achat_credits'),
    path('callback/kkiapay/', views.callback_kkiapay, name='callback_kkiapay'),
    path('api/preparer/', views.api_preparer_paiement, name='api_preparer_paiement'),
    path('api/verifier/', views.verifier_paiement_ajax, name='verifier_paiement_ajax'),
]
