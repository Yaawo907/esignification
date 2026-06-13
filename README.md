# e-Signification Bénin — Guide de démarrage

## Stack technique
- Python 3.12 + Django 6.0.6
- SQLite (dev) / PostgreSQL (prod)
- Celery + Redis (tâches asynchrones)
- AES-256 Fernet (chiffrement fichiers)
- Merkle Tree + Certigna TSA (horodatage)

## Installation rapide

### 1. Prérequis
```bash
python3 -m venv venv
source venv/bin/activate
pip install django djangorestframework django-otp pyotp cryptography \
            celery redis django-environ reportlab weasyprint Pillow django-extensions
```

### 2. Configuration
```bash
cp .env.example .env
# Éditez .env et renseignez vos valeurs
# Générer une clé de chiffrement :
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Base de données
```bash
python manage.py migrate
python manage.py init_plateforme --email admin@votre-domaine.bj --password VotreMotDePasse
```

### 4. Fichiers statiques
```bash
python manage.py collectstatic
```

### 5. Démarrage développement
```bash
python manage.py runserver
```
Ouvrir : http://localhost:8000
Admin : admin@esignification.bj / AdminSecure2024!

### 6. Worker Celery (dans un autre terminal)
```bash
celery -A taches.celery_app worker --loglevel=info
celery -A taches.celery_app beat --loglevel=info
```

## Comptes créés par défaut

| Rôle | Email | Mot de passe |
|------|-------|--------------|
| Admin | admin@esignification.bj | AdminSecure2024! |
| Huissier test | huissier.test@etude.bj | TestPassword123! |
| Justiciable test | justiciable@gmail.com | TestPassword456! |

⚠️ **Changez ces mots de passe avant tout déploiement !**

## Architecture des fichiers

```
esignification/          # Configuration Django
accounts/                # Modèle User, auth, MFA, tokens
huissiers/               # Profils huissiers et clercs
justiciables/            # Profils justiciables
significations/          # Flux de signification, certificats
administration/          # Config plateforme, Certigna, audit
notifications/           # Service d'envoi d'emails
securite/                # Chiffrement, Merkle, tokens, audit
taches/                  # Celery (relances, lot Merkle quotidien)
api/                     # Endpoints AJAX (REST framework)
templates/               # Templates HTML par module
static/css/main.css      # Styles principaux
static/js/main.js        # JS (spinners, AJAX sécurisé)
```

## Sécurité
- **URLs** : UUID public uniquement (jamais la PK entière)
- **Fichiers** : chiffrement AES-256 Fernet en base
- **Authentification** : 2FA obligatoire (email / TOTP / SMS)
- **XSS** : échappement systématique via `escape()` Django
- **CSRF** : token sur chaque formulaire et requête AJAX
- **Audit** : piste immuable (écriture seule, suppression interdite)
- **HTTPS** : à activer via Nginx en production

## Horodatage Certigna
Activez le bouton bascule dans **Administration → Configuration → Horodatage Certigna**.
Renseignez vos identifiants API Certigna. Le lot Merkle quotidien consomme
1 jeton par jour, quel que soit le volume d'actes.

## Déploiement production

### Nginx + Gunicorn
```bash
pip install gunicorn
gunicorn esignification.wsgi:application --workers 4 --bind 0.0.0.0:8000
```

### Variables .env production
```
DEBUG=False
ALLOWED_HOSTS=votre-domaine.bj
DATABASE_URL=postgres://user:password@localhost/esignification
SECRET_KEY=<clé longue et aléatoire>
```
