import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Conversation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)),
                ('sujet', models.CharField(max_length=255)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('date_dernier_message', models.DateTimeField(auto_now_add=True)),
                ('archivee_p1', models.BooleanField(default=False)),
                ('archivee_p2', models.BooleanField(default=False)),
                ('participant_1', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='conversations_p1', to=settings.AUTH_USER_MODEL)),
                ('participant_2', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='conversations_p2', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Conversation', 'ordering': ['-date_dernier_message']},
        ),
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)),
                ('contenu_chiffre', models.BinaryField()),
                ('date_envoi', models.DateTimeField(auto_now_add=True)),
                ('lu', models.BooleanField(default=False)),
                ('date_lecture', models.DateTimeField(blank=True, null=True)),
                ('auteur', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='messages_envoyes', to=settings.AUTH_USER_MODEL)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='messages', to='messagerie.conversation')),
            ],
            options={'verbose_name': 'Message', 'ordering': ['date_envoi']},
        ),
        migrations.CreateModel(
            name='PieceJointeMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)),
                ('fichier_chiffre', models.BinaryField()),
                ('nom_fichier', models.CharField(max_length=255)),
                ('taille_octets', models.IntegerField(default=0)),
                ('type_mime', models.CharField(blank=True, max_length=100)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                    related_name='pieces_jointes', to='messagerie.message')),
            ],
            options={'verbose_name': 'Pièce jointe message'},
        ),
    ]
