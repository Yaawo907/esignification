import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_alter_tokenactivation_type_token'),
        ('administration', '0003_yousign_config'),
    ]

    operations = [
        migrations.CreateModel(
            name='AcceptationTexteLegal',
            fields=[
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True)),
                ('type_texte', models.CharField(choices=[('cgu', "Conditions Générales d'Utilisation"), ('mentions', 'Mentions légales'), ('confidentialite', 'Politique de confidentialité')], max_length=20)),
                ('version', models.CharField(max_length=20)),
                ('langue', models.CharField(max_length=5)),
                ('hash_contenu', models.CharField(help_text='Empreinte SHA-256 du contenu accepté', max_length=64)),
                ('contexte', models.CharField(choices=[('inscription_huissier', 'Inscription huissier'), ('inscription_justiciable', 'Inscription justiciable'), ('inscription_clerc', 'Inscription clerc'), ('reacceptation_connexion', 'Réacceptation à la connexion')], max_length=30)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=500)),
                ('date_acceptation', models.DateTimeField(auto_now_add=True)),
                ('texte_legal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='acceptations', to='administration.textelegal')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acceptations_textes_legaux', to='accounts.user')),
            ],
            options={
                'verbose_name': 'Acceptation de texte légal',
                'verbose_name_plural': 'Acceptations de textes légaux',
                'ordering': ['-date_acceptation'],
                'indexes': [models.Index(fields=['user', 'type_texte', '-date_acceptation'], name='administrat_user_id_6f0a0d_idx')],
            },
        ),
    ]
