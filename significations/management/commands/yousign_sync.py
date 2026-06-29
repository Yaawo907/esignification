"""
Synchronise les significations en attente de signature Yousign.

Usage en développement local (sans webhook public) :
  python manage.py yousign_sync
  python manage.py yousign_sync --reference SIG-2026-0004
"""
from django.core.management.base import BaseCommand

from significations.models import Signification
from significations.yousign_service import recuperer_statut_yousign
from significations.views import finaliser_yousign_et_envoyer_justiciable


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
            sig_req_id = sig.yousign_signature_request_id
            try:
                statut_ys = recuperer_statut_yousign(sig_req_id)
            except Exception as exc:
                self.stderr.write(f"{sig.reference} : erreur API Yousign — {exc}")
                continue

            if statut_ys == 'done':
                try:
                    finaliser_yousign_et_envoyer_justiciable(sig, sig_req_id)
                except Exception as exc:
                    self.stderr.write(f"{sig.reference} : échec finalisation — {exc}")
                    continue
                self.stdout.write(self.style.SUCCESS(
                    f"{sig.reference} : signature reçue, justiciable notifié."
                ))
            else:
                self.stdout.write(
                    f"{sig.reference} : statut Yousign = {statut_ys or 'inconnu'} (pas encore signé)."
                )
