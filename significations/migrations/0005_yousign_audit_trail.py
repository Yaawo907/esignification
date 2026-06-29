from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0004_alter_signification_statut'),
    ]

    operations = [
        migrations.AddField(
            model_name='signification',
            name='yousign_signer_id',
            field=models.CharField(blank=True, help_text='ID du signataire Yousign (huissier)', max_length=100),
        ),
        migrations.AddField(
            model_name='signification',
            name='yousign_audit_trail_chiffre',
            field=models.BinaryField(blank=True, help_text='Dossier de preuve Yousign (audit trail PDF chiffré)', null=True),
        ),
    ]
