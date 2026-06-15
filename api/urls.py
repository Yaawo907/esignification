from django.urls import path
from . import views
app_name = 'api'
urlpatterns = [
    path('justiciables/rechercher/', views.rechercher_justiciable_ajax, name='rechercher_justiciable'),
    path('huissier/stats/', views.statistiques_huissier_ajax, name='stats_huissier'),
    path('notifications/', views.notifications_ajax, name='notifications'),
    path('certigna/tester/', views.tester_certigna_ajax, name='tester_certigna'),
    path('yousign/tester/', views.tester_yousign_ajax, name='tester_yousign'),
]
