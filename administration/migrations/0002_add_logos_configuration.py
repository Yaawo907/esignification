from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('administration', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='configurationplateforme',
            name='logo_pays',
            field=models.ImageField(
                blank=True,
                help_text='Logo/armoiries du pays (PNG/JPG, fond transparent recommandé)',
                null=True,
                upload_to='logos/',
            ),
        ),
        migrations.AddField(
            model_name='configurationplateforme',
            name='logo_chambre',
            field=models.ImageField(
                blank=True,
                help_text='Logo de la Chambre Nationale des Huissiers de Justice',
                null=True,
                upload_to='logos/',
            ),
        ),
    ]
