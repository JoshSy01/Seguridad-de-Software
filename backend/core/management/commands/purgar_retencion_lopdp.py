from django.core.management.base import BaseCommand

from core.services import ejecutar_purga_retencion_lopdp


class Command(BaseCommand):
    help = "Ejecuta la política LOPDP de purga irreversible tras 5 años de retención máxima (Req. 114)."

    def handle(self, *args, **options):
        resultado = ejecutar_purga_retencion_lopdp()
        self.stdout.write(
            self.style.SUCCESS(
                f"Política LOPDP ejecutada (corte {resultado['fecha_corte']}, máx {resultado['plazo_maximo_anios']} años): "
                f"{resultado['registros_purgados']} registros expirados purgados."
            )
        )

