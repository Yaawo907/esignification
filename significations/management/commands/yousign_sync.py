"""
Synchronise les significations en attente de signature Yousign.

Usage en développement local (sans webhook public) ou en secours production :
  python manage.py yousign_sync
  python manage.py yousign_sync --reference SIG-2026-0004
"""
from django.core.management.base import BaseCommand

from significations.models import Signification
from significations.views import synchroniser_signification_yousign


class Command(BaseCommand):
    help = (
        "Vérifie le statut Yousign des actes en attente de signature huissier "
        "et envoie l'invitation au justiciable si la signature est terminée."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reference',
            help="Référence de la signification (ex. SIG-2026-0004)",
        )

    def handle(self, *args, **options):
        qs = Signification.objects.filter(
            statut=Signification.STATUT_ATTENTE_SIGNATURE,
        ).exclude(yousign_signature_request_id='')

        ref = options.get('reference')
        if ref:
            qs = qs.filter(reference=ref)

        if not qs.exists():
            self.stdout.write("Aucune signification en attente de signature Yousign.")
            return

        for sig in qs:
            ok, message = synchroniser_signification_yousign(sig)
            if ok:
                self.stdout.write(self.style.SUCCESS(f"{sig.reference} : {message}"))
            else:
                self.stdout.write(f"{sig.reference} : {message}")
