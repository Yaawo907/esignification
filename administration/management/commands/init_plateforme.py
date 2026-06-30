"""
Commande d'initialisation de la plateforme :
- Crée la configuration par défaut
- Crée les modèles d'emails par défaut
- Crée le compte administrateur initial
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Initialise la plateforme e-Signification'

    def add_arguments(self, parser):
        parser.add_argument('--email', default='admin@esignification.bj')
        parser.add_argument('--password', default='AdminSecure2024!')

    def handle(self, *args, **options):
        self.stdout.write('=== Initialisation de la plateforme e-Signification Bénin ===\n')

        # 1. Configuration plateforme
        from administration.models import ConfigurationPlateforme, ModeleEmail, TexteLegal
        config = ConfigurationPlateforme.get()
        config.nom_plateforme = 'e-Signification Bénin'
        config.pays = 'Bénin'
        config.langue_defaut = 'fr'
        config.article_loi_signification = 'Loi n° 2017-20 du 20 avril 2018 portant code du numérique en République du Bénin'
        config.decret_reference = 'Décret d\'application en cours'
        config.nom_autorite_tutelle = 'Ministère de la Justice et de la Législation'
        config.delai_relance_1_jours = 3
        config.delai_relance_2_jours = 7
        config.methode_2fa_defaut = 'email'
        config.copyright_texte = '© 2024 e-Signification Bénin — Tous droits réservés'
        config.email_contact = options['email']
        config.save()
        self.stdout.write(self.style.SUCCESS('✓ Configuration plateforme créée'))

        # 1b. Textes légaux par défaut (CGU + politique de confidentialité)
        from pathlib import Path
        data_dir = Path(__file__).resolve().parent.parent.parent / 'data' / 'fr'
        textes_defaut = [
            (TexteLegal.TYPE_CGU, 'Conditions Générales d\'Utilisation', 'cgu.html'),
            (TexteLegal.TYPE_CONFIDENTIALITE, 'Politique de confidentialité', 'confidentialite.html'),
            (TexteLegal.TYPE_MENTIONS, 'Mentions légales', 'mentions.html'),
        ]
        for type_texte, titre, fichier in textes_defaut:
            chemin = data_dir / fichier
            contenu = chemin.read_text(encoding='utf-8') if chemin.exists() else f'<p>{titre} — contenu à compléter.</p>'
            obj, created = TexteLegal.objects.get_or_create(
                type_texte=type_texte, langue='fr',
                defaults={'titre': titre, 'contenu_html': contenu, 'version': '1.0'},
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Texte légal : {titre}'))
            elif not obj.contenu_html.strip():
                obj.contenu_html = contenu
                obj.save(update_fields=['contenu_html'])
                self.stdout.write(self.style.WARNING(f'  ! Texte légal complété : {titre}'))

        # 2. Modèles d'emails par défaut
        modeles = [
            {
                'type_email': 'activation_huissier',
                'langue': 'fr',
                'sujet': 'Activez votre compte Huissier — {{ config.nom_plateforme }}',
                'corps_html': '<p>Cliquez sur <a href="{{ lien_activation }}">ce lien</a> pour activer votre compte (valable {{ expiry_heures }}h).</p>',
            },
            {
                'type_email': 'invitation_justiciable',
                'langue': 'fr',
                'sujet': 'Invitation à créer votre compte — {{ config.nom_plateforme }}',
                'corps_html': '<p>Vous avez été invité(e) à créer votre compte. <a href="{{ lien_invitation }}">Cliquez ici</a>.</p>',
            },
        ]
        for m in modeles:
            obj, created = ModeleEmail.objects.get_or_create(
                type_email=m['type_email'], langue=m['langue'],
                defaults={'sujet': m['sujet'], 'corps_html': m['corps_html']}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Modèle email : {m["type_email"]}'))

        # 3. Compte administrateur
        email = options['email']
        password = options['password']
        if not User.objects.filter(email=email).exists():
            admin = User.objects.create_superuser(
                email=email,
                password=password,
                role=User.ADMIN,
                is_active=True,
            )
            from administration.models import ProfilAdmin
            ProfilAdmin.objects.get_or_create(
                user=admin,
                defaults={'nom': 'Administrateur', 'prenom': ''},
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Compte admin créé : {email}'))
            self.stdout.write(self.style.WARNING(f'  → Mot de passe : {password}'))
            self.stdout.write(self.style.WARNING('  → CHANGEZ ce mot de passe en production !'))
        else:
            self.stdout.write(self.style.WARNING(f'! Compte admin existant : {email}'))

        self.stdout.write('\n' + self.style.SUCCESS('=== Initialisation terminée ==='))
        self.stdout.write('Démarrez le serveur : python manage.py runserver')
