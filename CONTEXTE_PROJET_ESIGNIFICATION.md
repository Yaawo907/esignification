# CONTEXTE PROJET — e-Signification Bénin
> Document de référence à fournir à Claude avant tout travail sur ce projet.
> Dernière mise à jour : juin 2026

---

## 1. DESCRIPTION DU PROJET

**e-Signification Bénin** est une plateforme web métier permettant aux **huissiers de justice** de signifier électroniquement des actes judiciaires aux **justiciables** (particuliers et entreprises) au Bénin.

- Application **Django 5.2.13 + Python 3.11/3.12**
- Projet installé localement sur : `C:\Users\LENOVO\Desktop\esignification_benin\`
- URL de développement : `http://localhost:8000`
- Démarrage : `python manage.py runserver` (dans le dossier avec venv activé)

---

## 2. ACTEURS ET RÔLES

| Rôle | Description | Espace |
|------|-------------|--------|
| **Administrateur** | Gère la plateforme, crée les huissiers | `/administration/` |
| **Huissier titulaire** | Envoie les significations, gère son étude | `/huissier/` |
| **Clerc assermenté** | Droits limités, pas de configuration | `/huissier/` |
| **Justiciable** | Reçoit et répond aux significations | `/justiciable/` |

**Compte admin par défaut :**
- Email : `admin@esignification.bj`
- Mot de passe : `AdminSecure2024!`

---

## 3. STRUCTURE DES DOSSIERS

```
esignification_benin/
│
├── manage.py
├── requirements.txt
├── .env                          ← variables d'environnement
│
├── esignification/               ← configuration Django
│   ├── settings.py
│   └── urls.py                   ← URLs principales
│
├── accounts/                     ← utilisateurs, auth, 2FA, tokens
│   ├── models.py                 ← User custom, TokenActivation
│   ├── views.py                  ← connexion, inscription, MFA, récupération MDP
│   ├── forms.py                  ← tous les formulaires auth
│   └── urls.py
│
├── huissiers/                    ← profils huissiers et clercs
│   ├── models.py                 ← ProfilHuissier, ProfilClerc
│   ├── views.py                  ← tableau de bord, recherche, invitations
│   └── urls.py
│
├── justiciables/                 ← profils justiciables
│   ├── models.py                 ← ProfilJusticiable, InvitationJusticiable
│   ├── views.py                  ← tableau de bord, liste, réponses
│   └── urls.py
│
├── significations/               ← cœur métier
│   ├── models.py                 ← Signification, Certificat, Réponse, Relance
│   ├── views.py                  ← envoi, réception, certificats PDF, téléchargements
│   └── urls.py
│
├── administration/               ← espace admin
│   ├── models.py                 ← ConfigurationPlateforme, TexteLegal, LotMerkle, PisteAudit
│   ├── views.py                  ← tableau de bord, huissiers, config, audit
│   ├── urls.py
│   └── context_processors.py    ← config disponible dans tous les templates
│
├── notifications/                ← emails
│   └── service.py                ← envoi emails (activation, invitation, signification, certificat)
│
├── securite/                     ← sécurité transversale
│   ├── chiffrement.py            ← AES-256 Fernet (chiffrer/déchiffrer fichiers)
│   ├── merkle.py                 ← arbre de Merkle (horodatage)
│   ├── tokens.py                 ← génération/validation tokens
│   ├── audit.py                  ← journaliser() — piste d'audit
│   └── middleware.py             ← AuditMiddleware, SecuriteHeadersMiddleware
│
├── taches/                       ← Celery (tâches asynchrones)
│   ├── celery_app.py
│   └── tasks.py                  ← relances auto, lot Merkle quotidien Certigna
│
├── api/                          ← endpoints AJAX
│   ├── views.py                  ← recherche justiciable, stats, notifications, test Certigna
│   └── urls.py
│
├── templates/
│   ├── base/
│   │   └── base.html             ← template parent (spinner global SVG inclus)
│   ├── accounts/                 ← connexion, inscription, MFA, récupération
│   ├── huissiers/                ← tableau de bord huissier
│   ├── justiciables/             ← tableau de bord justiciable
│   ├── administration/           ← espace admin (config, huissiers, audit)
│   └── significations/           ← envoi, réponse, certificat
│
├── static/
│   ├── css/main.css              ← TOUT le CSS (variables CSS, composants)
│   └── js/main.js                ← TOUT le JS (spinners, AJAX sécurisé, XSS)
│
└── administration/management/commands/
    └── init_plateforme.py        ← commande d'initialisation
```

---

## 4. RÈGLES DE DÉVELOPPEMENT OBLIGATOIRES

Ces règles sont **non négociables** et doivent être respectées dans chaque modification :

### Sécurité
- **URLs** : utiliser uniquement les **UUID publics** (`sig.uuid`, `profil.uuid`), jamais les PK entières (`sig.pk`, `profil.id`)
- **XSS** : toujours échapper les données utilisateur avec `escape()` de Django avant de les stocker ou afficher
- **CSRF** : token `{% csrf_token %}` dans chaque formulaire HTML, header `X-CSRFToken` dans chaque requête AJAX
- **Chiffrement** : tous les fichiers PDF sont chiffrés AES-256 Fernet avant stockage (via `securite/chiffrement.py`)
- **Piste d'audit** : appeler `journaliser()` pour toute action importante (connexion, envoi, téléchargement…)
- **Validation serveur** : toujours valider les données côté serveur (views.py), jamais faire confiance au front seul

### Design et UX
- **Couleurs principales** : bleu marine `#1a3c6e` (huissier/admin), vert teal `#134e3a` (justiciable)
- **Design épuré**, fond subtil `#f5f6fa`, fort contraste
- **Spinner global** : SVG animé "remise de document d'une main à l'autre" — déjà dans `base.html`
- **Spinner sur boutons** : utiliser la classe `btn-spinner` + `data-loading="texte..."` sur les boutons de formulaire
- **Spinner sur liens** : ajouter la classe `spinner-link` sur les liens de navigation
- **Spinner téléchargement** : attribut `data-loading="Téléchargement…"` sur les liens de download
- Ne pas utiliser de frameworks CSS externes (Bootstrap, Tailwind) — le CSS est dans `static/css/main.css`

### Architecture
- **AJAX** : utiliser la fonction `fetchSecure()` définie dans `main.js` (gère CSRF automatiquement)
- **Pas d'innerHTML** avec données utilisateur — utiliser `textContent` ou la fonction `buildSearchItem()` de `main.js`
- Les endpoints AJAX sont dans `api/views.py` et préfixés `/api/`
- Toujours utiliser `@login_required` + vérification du rôle dans chaque vue

---

## 5. FLUX MÉTIER PRINCIPAL

### Création d'un compte huissier (2 étapes)
1. **Admin** saisit uniquement l'email officiel → lien d'activation envoyé (valable 72h)
2. **Huissier** clique le lien → remplit nom, prénom, étude, IFU, NPI, adresse, téléphone, mot de passe → connecté directement au dashboard

### Flux de signification
1. Huissier recherche le justiciable (par NPI, IFU, email, nom)
2. Huissier joint l'acte PDF signé + coche "nécessite réponse" si besoin
3. Email envoyé au justiciable avec boutons **Accepter** / **Refuser**
4. **Acceptation** → horodatage instantané → génération certificat PDF → envoi copies (huissier + justiciable)
5. Si réponse requise → justiciable remplit et clique "Informer l'huissier" → horodatage réception
6. Une fois répondu → document verrouillé, non modifiable

### Relances automatiques (Celery)
- Relance 1 : après N jours (configurable dans admin, défaut 3j)
- Relance 2 : après N jours (configurable, défaut 7j)
- Après relance 2 : constat de non-réception PDF généré automatiquement
- L'huissier peut basculer manuellement en "signification traditionnelle"

---

## 6. MODÈLES DE DONNÉES CLÉS

### `accounts.User` (custom)
```python
- id (PK interne, ne jamais exposer)
- uuid (UUID public, utiliser dans les URLs)
- email (identifiant de connexion)
- role : 'admin' | 'huissier' | 'clerc' | 'justiciable'
- is_active
- mfa_methode : 'email' | 'otp' | 'totp'
- mfa_active, mfa_code, mfa_code_expiry, totp_secret
```

### `significations.Signification`
```python
- uuid (utiliser dans les URLs)
- reference (ex: SIG-2026-0001, auto-générée)
- huissier → ProfilHuissier
- justiciable → ProfilJusticiable
- fichier_chiffre (PDF chiffré AES-256)
- necessite_reponse (bool)
- statut : en_attente | acceptee | refusee | relance_1 | relance_2 | non_delivree | traditionnelle | repondu
- hash_acte (SHA-256 du fichier original)
```

### `administration.ConfigurationPlateforme` (singleton, pk=1)
```python
- nom_plateforme, pays, langue_defaut
- article_loi_signification, decret_reference
- delai_relance_1_jours, delai_relance_2_jours
- methode_2fa_defaut
- certigna_active (bool — bouton bascule ON/OFF)
- certigna_tsa_url, certigna_login, certigna_password_chiffre
- certigna_heure_lot, certigna_seuil_alerte_jetons, certigna_jetons_restants
```

### `administration.PisteAudit` (immuable)
```python
# Écriture seule — les méthodes save() et delete() empêchent toute modification
- action, user_email, objet_type, objet_uuid, description, ip_address, date
```

---

## 7. URLS IMPORTANTES

| URL | Vue | Description |
|-----|-----|-------------|
| `/connexion/` | `accounts:connexion` | Page de connexion |
| `/inscription/huissier/?token=...` | `accounts:inscription_huissier` | Activation compte huissier |
| `/inscription/justiciable/?token=...` | `accounts:inscription_justiciable` | Création compte justiciable |
| `/administration/` | `administration:tableau_de_bord` | Dashboard admin |
| `/administration/huissiers/creer/` | `administration:creer_huissier` | Créer un huissier (email seul) |
| `/administration/configuration/` | `administration:configuration` | Config + Certigna toggle |
| `/huissier/` | `huissiers:tableau_de_bord` | Dashboard huissier |
| `/huissier/rechercher/` | `huissiers:rechercher` | Recherche justiciable |
| `/justiciable/` | `justiciables:tableau_de_bord` | Dashboard justiciable |
| `/significations/envoyer/` | `significations:envoyer` | Envoyer un acte |
| `/significations/repondre/<uuid>/` | `significations:repondre` | Accepter/refuser (lien email) |
| `/api/justiciables/rechercher/?q=` | `api:rechercher_justiciable` | AJAX recherche |
| `/api/notifications/` | `api:notifications` | AJAX polling notifications |

---

## 8. VARIABLES D'ENVIRONNEMENT (.env)

```env
SECRET_KEY=dev-secret-key-change-in-production
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=sqlite:///db.sqlite3
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=noreply@esignification.bj
EMAIL_HOST_PASSWORD=your-email-password
DEFAULT_FROM_EMAIL=e-Signification Bénin <noreply@esignification.bj>
CELERY_BROKER_URL=redis://localhost:6379/0
ENCRYPTION_KEY=<clé Fernet générée>
SITE_URL=http://localhost:8000
ACTIVATION_TOKEN_EXPIRY_HOURS=72
```

---

## 9. COMMANDES UTILES

```bash
# Activer l'environnement virtuel (Windows)
venv\Scripts\activate

# Démarrer le serveur
python manage.py runserver

# Après modification d'un models.py
python manage.py makemigrations
python manage.py migrate

# Réinitialiser les données de base
python manage.py init_plateforme

# Collecter les fichiers statiques
python manage.py collectstatic
```

---

## 10. CE QUI EST DÉJÀ DÉVELOPPÉ ✅

- [x] Modèles complets (User, Huissier, Justiciable, Signification, Certificat, Config, Audit)
- [x] Authentification complète avec 2FA (email / OTP / TOTP)
- [x] Flux création huissier (admin envoie email → huissier complète profil → connecté auto)
- [x] Flux inscription justiciable (invitation → confirmation domicile électronique)
- [x] Envoi de signification avec chiffrement AES-256
- [x] Acceptation/refus via lien email avec horodatage
- [x] Génération certificat PDF (reportlab)
- [x] Téléchargement actes et certificats (inline, pas forcé)
- [x] Réponse justiciable → notification huissier
- [x] Piste d'audit immuable
- [x] Configuration plateforme (singleton)
- [x] Bouton bascule Certigna ON/OFF avec panneau de config
- [x] Arbre de Merkle + lot quotidien Certigna (taches/tasks.py)
- [x] Relances automatiques Celery (relance 1, relance 2, constat)
- [x] API AJAX (recherche, stats, notifications, test Certigna)
- [x] CSS complet (static/css/main.css)
- [x] JS complet avec sécurité XSS (static/js/main.js)
- [x] Spinner global SVG "remise de document"
- [x] Templates : connexion, inscription huissier/justiciable, dashboards, admin, significations
- [x] Page liste huissiers admin (avec AJAX activer/désactiver, renvoyer invitation)
- [x] Page invitation justiciable huissier (formulaire + historique + renvoyer AJAX)

## 11. CE QUI RESTE À FAIRE 🔲

- [ ] Page d'accueil publique (landing page)
- [ ] Page CGU (`/cgu/`) et Politique de confidentialité (`/confidentialite/`)
- [ ] Templates complets : liste significations huissier, recherche justiciable (résultats détaillés)
- [ ] Gestion des clercs (création, affectation à un huissier)
- [ ] Intégration YouSign (signature électronique des actes)
- [ ] Multilingue EN/ES (traductions i18n)
- [ ] Configuration Nginx + Gunicorn pour déploiement production
- [ ] Tests unitaires formels (pytest-django)
- [ ] Gestion des actes multi-destinataires (saisies bancaires)
- [ ] Dashboard admin : gestion modèles d'emails
- [ ] Réplication multi-pays (Burkina, Mali…)

---

## 12. POINTS D'ATTENTION POUR CLAUDE

1. **Ne jamais exposer les PK** dans les URLs — toujours utiliser `.uuid`
2. **Ne jamais faire confiance aux données POST** sans `escape()` côté serveur
3. **Toujours vérifier le rôle** de l'utilisateur connecté dans chaque vue (huissier ≠ justiciable ≠ admin)
4. **La piste d'audit est immuable** — ne pas tenter de modifier ou supprimer `PisteAudit`
5. **Le CSS est centralisé** dans `static/css/main.css` — ne pas ajouter de `<style>` inline dans les templates sauf pour des ajustements très ponctuels
6. **Le JS est centralisé** dans `static/js/main.js` — utiliser `fetchSecure()` pour tout appel AJAX
7. **ConfigurationPlateforme** est un singleton — toujours accéder via `ConfigurationPlateforme.get()`
8. **Les fichiers PDF** doivent être chiffrés avec `chiffrer_fichier()` avant stockage et déchiffrés avec `dechiffrer_fichier()` à la lecture
9. **Design** : bleu marine `#1a3c6e` pour huissier/admin, vert `#134e3a` pour justiciable — ne pas changer la charte graphique
10. **Spinner** : classe `spinner-link` sur les liens de navigation, `btn-spinner` + `data-loading` sur les boutons de formulaire
