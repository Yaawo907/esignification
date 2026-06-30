from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('administration', '0006_profil_admin'),
        ('significations', '0007_reponsejusticiable_texte_hash'),
    ]

    operations = [
        migrations.AddField(
            model_name='reponsejusticiable',
            name='hash_annexe',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='hash_merkle',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='chemin_merkle',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='horodatage_certigna',
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='nom_fichier_annexe',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='lot_merkle',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to='administration.lotmerkle',
            ),
        ),
    ]
