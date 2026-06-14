import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('justiciables', '0001_initial'),
        ('huissiers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DemandeModificationProfil',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)),
                ('statut', models.CharField(choices=[('en_attente', 'En attente'), ('validee', 'Validée'), ('refusee', 'Refusée')], default='en_attente', max_length=20)),
                ('nouveau_nom', models.CharField(blank=True, max_length=100)),
                ('nouveau_prenom', models.CharField(blank=True, max_length=100)),
                ('nouveau_nom_entreprise', models.CharField(blank=True, max_length=200)),
                ('nouveau_telephone', models.CharField(blank=True, max_length=20)),
                ('nouvelle_adresse', models.TextField(blank=True)),
                ('nouveau_ifu', models.CharField(blank=True, max_length=50)),
                ('nouveau_npi', models.CharField(blank=True, max_length=50)),
                ('message_justiciable', models.TextField(blank=True, verbose_name='Message / motif de la demande')),
                ('piece_1_chiffree', models.BinaryField(blank=True, null=True)),
                ('piece_1_nom', models.CharField(blank=True, max_length=255)),
                ('piece_2_chiffree', models.BinaryField(blank=True, null=True)),
                ('piece_2_nom', models.CharField(blank=True, max_length=255)),
                ('motif_refus', models.TextField(blank=True)),
                ('date_traitement', models.DateTimeField(blank=True, null=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('justiciable', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='demandes_modification',
                    to='justiciables.profiljusticiable',
                )),
                ('huissier', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='demandes_modification_justiciables',
                    to='huissiers.profilhuissier',
                )),
            ],
            options={
                'verbose_name': 'Demande de modification de profil',
                'ordering': ['-date_creation'],
            },
        ),
    ]
