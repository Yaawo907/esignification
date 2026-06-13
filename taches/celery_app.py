from celery import Celery
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esignification.settings')
app = Celery('esignification')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
