import environ
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
env = environ.Env()
_ENV_FILE = BASE_DIR / '.env'
if _ENV_FILE.exists():
    # Priorité au .env local (évite qu'une variable système d'un autre projet Django écrase la config)
    environ.Env.read_env(_ENV_FILE, overwrite=True)

SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG', default=False)
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost'])
# En dev : accepter tout tunnel ngrok sans mettre à jour ALLOWED_HOSTS à chaque session
if DEBUG:
    for _ngrok_host in ('.ngrok-free.app', '.ngrok.io', '.ngrok.app'):
        if _ngrok_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_ngrok_host)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_email',
    'django_extensions',
    # Apps métier
    'accounts',
    'huissiers',
    'justiciables',
    'significations',
    'notifications',
    'administration',
    'securite',
    'taches',
    'api',
    'messagerie',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'securite.middleware.AuditMiddleware',
    'securite.middleware.SecuriteHeadersMiddleware',
]

ROOT_URLCONF = 'esignification.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'django.template.context_processors.csrf',
                'administration.context_processors.config_plateforme',
                'huissiers.context_processors.sidebar_huissier',
            ],
        },
    },
]

WSGI_APPLICATION = 'esignification.wsgi.application'

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR}/db.sqlite3')
}

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalisation
LANGUAGE_CODE = 'fr'
LANGUAGES = [
    ('fr', 'Français'),
    ('en', 'English'),
    ('es', 'Español'),
]
TIME_ZONE = 'Africa/Porto-Novo'
USE_I18N = True
USE_L10N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / 'locale']

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
# En production : WhiteNoise compresse et versionne les fichiers statiques
# En développement : storage par défaut (pas besoin de collectstatic)
if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email
def _resolve_email_backend():
    """Valide EMAIL_BACKEND — fallback console si chemin invalide (ex. apps.* d'un autre projet)."""
    import logging
    from django.utils.module_loading import import_string
    default = 'django.core.mail.backends.console.EmailBackend'
    backend = env('EMAIL_BACKEND', default=default)
    if not str(backend).startswith('django.core.mail.backends.'):
        logging.getLogger(__name__).warning(
            'EMAIL_BACKEND invalide (%r) — utilisation du backend console.', backend,
        )
        return default
    try:
        import_string(backend)
        return backend
    except Exception as exc:
        logging.getLogger(__name__).warning(
            'Impossible de charger EMAIL_BACKEND %r (%s) — fallback console.', backend, exc,
        )
        return default


EMAIL_BACKEND = _resolve_email_backend()
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=465)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@esignification.bj')
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=30)  # Timeout SMTP en secondes

# SMS (MFA OTP) — console | twilio | custom
SMS_BACKEND = env('SMS_BACKEND', default='console')
TWILIO_ACCOUNT_SID = env('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = env('TWILIO_AUTH_TOKEN', default='')
TWILIO_FROM_NUMBER = env('TWILIO_FROM_NUMBER', default='')
# API personnalisée (votre propre service SMS)
SMS_API_URL = env('SMS_API_URL', default='')
SMS_API_KEY = env('SMS_API_KEY', default='')
SMS_SENDER = env('SMS_SENDER', default='eSignification')
SMS_API_AUTH_STYLE = env('SMS_API_AUTH_STYLE', default='bearer')  # bearer | header
SMS_API_KEY_HEADER = env('SMS_API_KEY_HEADER', default='X-API-Key')
SMS_API_TIMEOUT = env.int('SMS_API_TIMEOUT', default=30)
# Passerelle derrière POST /api/v1/sms/ : console | twilio | webhook | smspartner
SMS_GATEWAY_PROVIDER = env('SMS_GATEWAY_PROVIDER', default='console')
SMS_GATEWAY_WEBHOOK_URL = env('SMS_GATEWAY_WEBHOOK_URL', default='')
SMS_GATEWAY_WEBHOOK_KEY = env('SMS_GATEWAY_WEBHOOK_KEY', default='')

# MFA — authentification par SMS (OTP) : désactivée par défaut
MFA_SMS_ENABLED = env.bool('MFA_SMS_ENABLED', default=False)
# SMSPartner (https://api.smspartner.fr/v1/send)
SMSPARTNER_API_KEY = env('SMSPARTNER_API_KEY', default='')
SMSPARTNER_GAMME = env.int('SMSPARTNER_GAMME', default=1)
# Callback livraison SMS (optionnel) — URL publique de VOTRE site, pas l'URL d'envoi
SMSPARTNER_WEBHOOK_URL = env('SMSPARTNER_WEBHOOK_URL', default='')


# Celery
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = env('CELERY_BROKER_URL', default='redis://localhost:6379/0')
CELERY_TIMEZONE = TIME_ZONE
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'

# Chiffrement
ENCRYPTION_KEY = env('ENCRYPTION_KEY')

# Services tiers
YOUSIGN_API_KEY = env('YOUSIGN_API_KEY', default='')
YOUSIGN_API_URL = env('YOUSIGN_API_URL', default='https://api.yousign.app/v3')
YOUSIGN_WEBHOOK_SECRET = env('YOUSIGN_WEBHOOK_SECRET', default='') or env('WEBHOOK_SECRET', default='')
CERTIGNA_TSA_URL = env('CERTIGNA_TSA_URL', default='')
CERTIGNA_LOGIN = env('CERTIGNA_LOGIN', default='')
CERTIGNA_PASSWORD = env('CERTIGNA_PASSWORD', default='')

SITE_URL = env('SITE_URL', default='http://localhost:8000')
ACTIVATION_TOKEN_EXPIRY_HOURS = env.int('ACTIVATION_TOKEN_EXPIRY_HOURS', default=72)

# Sécurité
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True

# Sécurité HTTPS (production uniquement — activé quand DEBUG=False)
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Proxy SSL (Render, nginx, Caddy…) — Django sait que la requête client est en HTTPS
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Redirection HTTP → HTTPS
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    # HSTS — force HTTPS dans le navigateur (désactiver temporairement : SECURE_HSTS_SECONDS=0)
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
    # Domaines autorisés pour les requêtes CSRF (obligatoire Django 4+ sur HTTPS)
    CSRF_TRUSTED_ORIGINS = env.list(
        'CSRF_TRUSTED_ORIGINS',
        default=['https://esignification.onrender.com'],
    )

LOGIN_URL = '/connexion/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/connexion/'

# DRF
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
}
