# Generated manually for ProfilAdmin

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def creer_profils_admin_existants(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    ProfilAdmin = apps.get_model('administration', 'ProfilAdmin')
    for user in User.objects.filter(role='admin'):
        ProfilAdmin.objects.get_or_create(
            user=user,
            defaults={'nom': 'Administrateur', 'prenom': ''},
        )


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('administration', '0005_rename_administrat_user_id_6f0a0d_idx_administrat_user_id_62825c_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfilAdmin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ('nom', models.CharField(max_length=100)),
                ('prenom', models.CharField(blank=True, max_length=100)),
                ('telephone', models.CharField(blank=True, max_length=20)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profil_admin',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Profil administrateur',
            },
        ),
        migrations.RunPython(creer_profils_admin_existants, migrations.RunPython.noop),
    ]
