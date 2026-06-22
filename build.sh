#!/usr/bin/env bash
# Script de build pour Render
set -o errexit  # Arrête le script si une commande échoue

# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Collecter les fichiers statiques
python manage.py collectstatic --no-input

# 3. Appliquer les migrations
python manage.py migrate

# 4. (Optionnel) Créer le superutilisateur initial si aucun n'existe
# Décommente les lignes ci-dessous et adapte les valeurs
python create_superuser.py

python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'esignification.settings')
django.setup()
from django.core.mail import send_mail
send_mail('Test', 'Message test', 'noreply@esignification.bj', ['yawo907@gmail.com'])
print('Email envoyé !')
"
