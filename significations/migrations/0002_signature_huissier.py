from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='signification',
            name='signature_huissier_b64',
            field=models.TextField(blank=True),
        ),
    ]
