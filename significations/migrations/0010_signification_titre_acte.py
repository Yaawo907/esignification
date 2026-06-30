from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0009_chiffrer_texte_reponse'),
    ]

    operations = [
        migrations.AddField(
            model_name='signification',
            name='titre_acte',
            field=models.CharField(blank=True, max_length=300, verbose_name="Titre de l'acte"),
        ),
    ]
