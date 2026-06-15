from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0002_signature_huissier'),
    ]

    operations = [
        migrations.AddField(
            model_name='signification',
            name='yousign_signature_request_id',
            field=models.CharField(blank=True, db_index=True, max_length=100,
                help_text='ID de la demande de signature Yousign'),
        ),
        migrations.AddField(
            model_name='signification',
            name='yousign_statut',
            field=models.CharField(blank=True, max_length=30,
                help_text='Statut Yousign : pending, ongoing, done, rejected, expired, canceled'),
        ),
    ]
