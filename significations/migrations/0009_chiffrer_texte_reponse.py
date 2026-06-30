from django.db import migrations


def chiffrer_textes_reponses(apps, schema_editor):
    ReponseJusticiable = apps.get_model('significations', 'ReponseJusticiable')
    from securite.chiffrement import chiffrer_texte, dechiffrer_texte
    from html import unescape

    for reponse in ReponseJusticiable.objects.exclude(texte_reponse=''):
        try:
            dechiffrer_texte(reponse.texte_reponse)
            continue
        except Exception:
            pass
        texte = unescape(reponse.texte_reponse)
        reponse.texte_reponse = chiffrer_texte(texte)
        reponse.save(update_fields=['texte_reponse'])


class Migration(migrations.Migration):

    dependencies = [
        ('significations', '0008_reponsejusticiable_merkle_annexe'),
    ]

    operations = [
        migrations.RunPython(chiffrer_textes_reponses, migrations.RunPython.noop),
    ]
