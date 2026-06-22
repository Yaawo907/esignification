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
