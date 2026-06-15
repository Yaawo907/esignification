from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('administration', '0002_add_logos_configuration'),
    ]

    operations = [
        migrations.AddField(
            model_name='configurationplateforme',
            name='yousign_active',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='configurationplateforme',
            name='yousign_mode',
            field=models.CharField(
                choices=[('sandbox', 'Sandbox (test)'), ('production', 'Production')],
                default='sandbox',
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='configurationplateforme',
            name='yousign_api_key_chiffre',
            field=models.CharField(blank=True, max_length=500,
                help_text='Clé API Yousign — chiffrée AES-256 en base'),
        ),
        migrations.AddField(
            model_name='configurationplateforme',
            name='yousign_webhook_secret_chiffre',
            field=models.CharField(blank=True, max_length=500,
                help_text='Secret webhook Yousign pour valider les callbacks'),
        ),
    ]
