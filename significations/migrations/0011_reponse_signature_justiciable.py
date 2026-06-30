from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0010_signification_titre_acte'),
    ]

    operations = [
        migrations.AddField(
            model_name='reponsejusticiable',
            name='signature_justiciable_b64',
            field=models.TextField(blank=True, verbose_name='Signature visuelle du justiciable'),
        ),
    ]
