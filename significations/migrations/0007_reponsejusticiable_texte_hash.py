from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0006_signification_credit_ajuste_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='reponsejusticiable',
            name='texte_reponse',
            field=models.TextField(blank=True, verbose_name='Texte de la réponse'),
        ),
        migrations.AddField(
            model_name='reponsejusticiable',
            name='hash_contenu',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
