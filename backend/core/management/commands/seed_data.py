from datetime import date, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import CatalogoEstablecimiento, DelegacionFamiliar, HorarioMedico, Turno, User


class Command(BaseCommand):
    help = "Inicializa usuarios semilla, catálogo de establecimientos, horarios completos y citas base."

    def handle(self, *args, **options):
        establecimientos = [
            ("Hospital Carlos Andrade Marín (HCAM)", "Quito"),
            ("Centro de Salud IESS Cotocollao", "Quito"),
            ("Hospital del Día El Batán", "Quito"),
        ]
        for nombre, ciudad in establecimientos:
            CatalogoEstablecimiento.objects.update_or_create(
                nombre=nombre,
                defaults={"ciudad": ciudad, "activo": True},
            )

        seed_users = [
            {
                "cedula": "1710000017",
                "nombres": "Carlos Andrés Pérez (Titular)",
                "fecha_nacimiento": date(1990, 5, 15),
                "email": "carlos.perez@mail.com",
                "telefono": "0991234567",
                "rol": User.Rol.AFILIADO,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": False,
                "password": "ClaveSegura#IESS2026!",
            },
            {
                "cedula": "1710000025",
                "nombres": "María Fernanda Gómez (Externo)",
                "fecha_nacimiento": date(1985, 8, 22),
                "email": "maria.gomez@mail.com",
                "telefono": "0987654321",
                "rol": User.Rol.AFILIADO,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": False,
                "password": "ClaveSegura#IESS2026!",
            },
            {
                "cedula": "1710000033",
                "nombres": "Mateo Pérez (Hijo Menor)",
                "fecha_nacimiento": date(2016, 3, 10),
                "email": "mateo.menor@mail.com",
                "telefono": "0991234567",
                "rol": User.Rol.AFILIADO,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": False,
                "password": "ClaveSegura#IESS2026!",
            },
            {
                "cedula": "1710000041",
                "nombres": "Lucía Torres (Primer Ingreso)",
                "fecha_nacimiento": date(1995, 11, 20),
                "email": "lucia.torres@mail.com",
                "telefono": "0995556677",
                "rol": User.Rol.AFILIADO,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": True,
                "password": "Temporal#IESS2026!",
            },
            {
                "cedula": "1720000015",
                "nombres": "Ana Recepción IESS",
                "fecha_nacimiento": date(1992, 4, 12),
                "email": "recepcion@iess.gob.ec",
                "telefono": "0990001111",
                "rol": User.Rol.RECEPCION,
                "establecimiento_asignado": "Hospital Carlos Andrade Marín (HCAM)",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
            {
                "cedula": "1730000013",
                "nombres": "Dr. Roberto Salazar",
                "fecha_nacimiento": date(1980, 1, 25),
                "email": "dr.salazar@iess.gob.ec",
                "telefono": "0990002222",
                "rol": User.Rol.MEDICO,
                "establecimiento_asignado": "Hospital Carlos Andrade Marín (HCAM)",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
            {
                "cedula": "1730000021",
                "nombres": "Dra. Elena Viteri",
                "fecha_nacimiento": date(1982, 7, 19),
                "email": "dra.viteri@iess.gob.ec",
                "telefono": "0990002223",
                "rol": User.Rol.MEDICO,
                "establecimiento_asignado": "Hospital del Día El Batán",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
            {
                "cedula": "1730000039",
                "nombres": "Dr. Marco Paredes",
                "fecha_nacimiento": date(1984, 6, 11),
                "email": "dr.paredes@iess.gob.ec",
                "telefono": "0990002224",
                "rol": User.Rol.MEDICO,
                "establecimiento_asignado": "Centro de Salud IESS Cotocollao",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
            {
                "cedula": "1740000011",
                "nombres": "Ing. Javier Soporte",
                "fecha_nacimiento": date(1988, 9, 30),
                "email": "soporte@iess.gob.ec",
                "telefono": "0990003333",
                "rol": User.Rol.SOPORTE,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
            {
                "cedula": "1750000018",
                "nombres": "Dra. Patricia Admin",
                "fecha_nacimiento": date(1979, 12, 5),
                "email": "admin@iess.gob.ec",
                "telefono": "0990004444",
                "rol": User.Rol.ADMIN,
                "establecimiento_asignado": "",
                "debe_cambiar_clave": False,
                "password": "StaffSegura#IESS2026!",
            },
        ]

        for u_data in seed_users:
            raw_pwd = u_data.pop("password")
            user, created = User.objects.get_or_create(cedula=u_data["cedula"], defaults=u_data)
            if created or user.password.startswith("!seed_pending"):
                for k, v in u_data.items():
                    setattr(user, k, v)
                user.set_password(raw_pwd)
                user.intentos_fallidos = 0
                user.bloqueado_hasta = None
                user.is_active = True
                user.save()
            elif user.establecimiento_asignado != u_data["establecimiento_asignado"]:
                user.establecimiento_asignado = u_data["establecimiento_asignado"]
                user.save(update_fields=["establecimiento_asignado"])

        titular = User.objects.get(cedula="1710000017")
        hijo = User.objects.get(cedula="1710000033")
        externo = User.objects.get(cedula="1710000025")
        medico_1 = User.objects.get(cedula="1730000013")
        medico_2 = User.objects.get(cedula="1730000021")
        medico_3 = User.objects.get(cedula="1730000039")

        DelegacionFamiliar.objects.update_or_create(
            titular=titular,
            delegado=hijo,
            defaults={
                "tipo_vinculo": DelegacionFamiliar.TipoVinculo.HIJO_MENOR,
                "activo": True,
            },
        )

        # Cobertura completa de horarios (08:00 a 18:00) en los 3 establecimientos y las 4 especialidades
        mapa_medicos_establecimiento = [
            ("Hospital Carlos Andrade Marín (HCAM)", medico_1),
            ("Hospital del Día El Batán", medico_2),
            ("Centro de Salud IESS Cotocollao", medico_3),
        ]
        todas_especialidades = [esp for esp, _ in Turno.Especialidad.choices]

        for est_nombre, med_obj in mapa_medicos_establecimiento:
            for esp_nombre in todas_especialidades:
                HorarioMedico.objects.get_or_create(
                    medico=med_obj,
                    establecimiento=est_nombre,
                    especialidad=esp_nombre,
                    defaults={
                        "hora_inicio": time(8, 0),
                        "hora_fin": time(18, 0),
                        "intervalo_minutos": 30,
                        "activo": True,
                    },
                )

        hoy = timezone.localdate()
        futuro = hoy + timedelta(days=3)

        # Turno de hoy en HCAM para Médico 1 (Check-in Recepción HCAM y Agenda Médico 1)
        Turno.objects.get_or_create(
            medico=medico_1,
            fecha=hoy,
            hora=time(17, 30),
            defaults={
                "afiliado": hijo,
                "reservado_por": titular,
                "establecimiento": "Hospital Carlos Andrade Marín (HCAM)",
                "especialidad": "Pediatría",
                "estado": Turno.Estado.RESERVADO,
            },
        )

        # Turno de hoy en El Batán para Médico 2 (Prueba segregación Médico 1 vs Médico 2 y Recepción HCAM vs El Batán)
        Turno.objects.get_or_create(
            medico=medico_2,
            fecha=hoy,
            hora=time(17, 0),
            defaults={
                "afiliado": externo,
                "reservado_por": externo,
                "establecimiento": "Hospital del Día El Batán",
                "especialidad": "Psicología",
                "estado": Turno.Estado.RESERVADO,
            },
        )

        # Turno futuro de Afiliado Externo (>=24h) para probar bloqueo Anti-BOLA al cancelar
        Turno.objects.get_or_create(
            medico=medico_3,
            fecha=futuro,
            hora=time(10, 0),
            defaults={
                "afiliado": externo,
                "reservado_por": externo,
                "establecimiento": "Centro de Salud IESS Cotocollao",
                "especialidad": "Odontología",
                "estado": Turno.Estado.RESERVADO,
            },
        )

        self.stdout.write(
            self.style.SUCCESS("Datos semilla completos (catálogo, horarios 3x4 y citas) verificados.")
        )
