from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('huissiers', '0003_profilhuissier_solde_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='parametresignaturehuissier',
            name='yousign_zone_width',
            field=models.PositiveIntegerField(default=120),
        ),
        migrations.AddField(
            model_name='parametresignaturehuissier',
            name='yousign_zone_height',
            field=models.PositiveIntegerField(default=60),
        ),
    ]
