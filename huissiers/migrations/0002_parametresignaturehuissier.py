from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('huissiers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ParametreSignatureHuissier',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('signature_simple_b64', models.TextField(blank=True)),
                ('signature_simple_label', models.CharField(default='Signature simple', max_length=80)),
                ('signature_cachet_b64', models.TextField(blank=True)),
                ('signature_cachet_label', models.CharField(default='Signature avec cachet', max_length=80)),
                ('cachet_simple_b64', models.TextField(blank=True)),
                ('cachet_simple_label', models.CharField(default='Cachet simple', max_length=80)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('huissier', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='parametres_signature',
                    to='huissiers.profilhuissier',
                )),
            ],
            options={'verbose_name': 'Paramètres signature huissier'},
        ),
    ]
