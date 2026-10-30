import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models
from django.utils import timezone


def es_cedula_ecuatoriana_valida(cedula: str) -> bool:
    """
    Algoritmo oficial Módulo 10 del Registro Civil del Ecuador:
    - Exactamente 10 dígitos numéricos (no repetidos triviales).
    - Código de provincia: 01..24 o 30 (ecuatorianos en el exterior).
    - Tercer dígito menor a 6 (persona natural: 0..5).
    - Décimo dígito igual al verificador Módulo 10 con coeficientes [2,1,2,1,2,1,2,1,2].
    """
    if not isinstance(cedula, str):
        return False
    ced = cedula.strip()
    if len(ced) != 10 or not ced.isdigit():
        return False
    if len(set(ced)) == 1:
        return False

    provincia = int(ced[:2])
    if not ((1 <= provincia <= 24) or provincia == 30):
        return False

    tercer_digito = int(ced[2])
    if tercer_digito >= 6:
        return False

    coeficientes = (2, 1, 2, 1, 2, 1, 2, 1, 2)
    suma = 0
    for i in range(9):
        valor = int(ced[i]) * coeficientes[i]
        if valor >= 10:
            valor -= 9
        suma += valor

    digito_verificador = (10 - (suma % 10)) % 10
    return digito_verificador == int(ced[9])


def validador_cedula_ecuatoriana(value: str) -> None:
    if not es_cedula_ecuatoriana_valida(value):
        raise ValidationError(
            "Número de cédula ecuatoriana inválido (verifique provincia y dígito verificador Módulo 10)."
        )


def default_retencion_5_anios():
    return timezone.localdate() + timedelta(days=365 * 5)


class UserManager(BaseUserManager):
    def create_user(self, cedula, password=None, **extra_fields):
        if not cedula or not es_cedula_ecuatoriana_valida(str(cedula)):
            raise ValueError("Se requiere una cédula ecuatoriana válida.")
        if "email" in extra_fields:
            extra_fields["email"] = self.normalize_email(extra_fields["email"])
        user = self.model(cedula=str(cedula).strip(), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    """
    Modelo minimalista de usuario cumpliendo estrictamente con la LOPDP
    (Req. 102, 103, 104, 105, 114). Sin campos laborales, financieros ni clínicos.
    """

    class Rol(models.TextChoices):
        AFILIADO = "AFILIADO", "Afiliado"
        RECEPCION = "RECEPCION", "Recepción"
        MEDICO = "MEDICO", "Médico"
        ADMIN = "ADMIN", "Administrador"
        SOPORTE = "SOPORTE", "Soporte Técnico"

    cedula = models.CharField(
        max_length=10,
        primary_key=True,
        unique=True,
        validators=[validador_cedula_ecuatoriana],
    )
    nombres = models.CharField(max_length=150)
    fecha_nacimiento = models.DateField()
    email = models.EmailField(unique=True)
    telefono = models.CharField(max_length=15)
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.AFILIADO)
    establecimiento_asignado = models.CharField(max_length=120, blank=True, default="")
    debe_cambiar_clave = models.BooleanField(default=False)
    intentos_fallidos = models.IntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    objects = UserManager()

    USERNAME_FIELD = "cedula"
    REQUIRED_FIELDS = ["nombres", "fecha_nacimiento", "email", "telefono", "rol"]

    class Meta:
        db_table = "core_user"

    def __str__(self):
        return f"{self.cedula} - {self.nombres} ({self.rol})"


class CatalogoEstablecimiento(models.Model):
    nombre = models.CharField(max_length=120, unique=True)
    ciudad = models.CharField(max_length=80, default="Quito")
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "core_establecimiento"
        ordering = ["nombre"]


class DelegacionFamiliar(models.Model):
    class TipoVinculo(models.TextChoices):
        HIJO_MENOR = "HIJO_MENOR", "Hijo Menor"
        ADULTO_AUTORIZADO = "ADULTO_AUTORIZADO", "Adulto Autorizado"

    titular = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegaciones_otorgadas",
        db_column="titular_id",
    )
    delegado = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="delegaciones_recibidas",
        db_column="delegado_id",
    )
    tipo_vinculo = models.CharField(max_length=30, choices=TipoVinculo.choices)
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_delegacionfamiliar"
        constraints = [
            models.UniqueConstraint(fields=["titular", "delegado"], name="unique_titular_delegado")
        ]


class Turno(models.Model):
    class Especialidad(models.TextChoices):
        MEDICINA_GENERAL = "Medicina General", "Medicina General"
        ODONTOLOGIA = "Odontología", "Odontología"
        PSICOLOGIA = "Psicología", "Psicología"
        PEDIATRIA = "Pediatría", "Pediatría"

    class Estado(models.TextChoices):
        RESERVADO = "RESERVADO", "Reservado"
        CANCELADO = "CANCELADO", "Cancelado"
        ATENDIDO = "ATENDIDO", "Atendido"

    afiliado = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="turnos_beneficiario",
        db_column="afiliado_id",
    )
    reservado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="turnos_reservados",
        db_column="reservado_por_id",
    )
    medico = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="agenda_medico",
        db_column="medico_id",
    )
    establecimiento = models.CharField(max_length=120)
    especialidad = models.CharField(max_length=50, choices=Especialidad.choices)
    fecha = models.DateField()
    hora = models.TimeField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.RESERVADO)
    asistencia_confirmada = models.BooleanField(default=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    retencion_hasta = models.DateField(default=default_retencion_5_anios)

    class Meta:
        db_table = "core_turno"
        constraints = [
            models.UniqueConstraint(
                fields=["medico", "fecha", "hora"],
                condition=models.Q(estado="RESERVADO"),
                name="unique_medico_fecha_hora_activo",
            ),
            models.UniqueConstraint(
                fields=["establecimiento", "especialidad", "fecha", "hora"],
                condition=models.Q(estado="RESERVADO"),
                name="unique_est_esp_fecha_hora_activo",
            ),
        ]


class AuditLog(models.Model):
    """
    Registro de auditoría inmutable (WORM - Req. 111).
    Prohíbe modificaciones o eliminaciones tanto en ORM como en PostgreSQL.
    """

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario_cedula = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    rol = models.CharField(max_length=20, null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    metodo = models.CharField(max_length=10)
    ruta = models.CharField(max_length=255)
    payload_sanitizado = models.JSONField(default=dict)
    status_code = models.IntegerField()

    class Meta:
        db_table = "core_auditlog"
        ordering = ["-timestamp"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("Los registros de AuditLog son inmutables (Req. 111).")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("No se permite eliminar registros de AuditLog (Req. 111).")


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sesiones",
        db_column="usuario_id",
    )
    jti_refresh = models.CharField(max_length=128, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    mfa_verificado = models.BooleanField(default=False)
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    ultima_actividad = models.DateTimeField(auto_now=True)
    expira_en = models.DateTimeField()
    motivo_cierre = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "core_usersession"
        ordering = ["-ultima_actividad"]


class HorarioMedico(models.Model):
    medico = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="horarios",
        db_column="medico_id",
    )
    establecimiento = models.CharField(max_length=120)
    especialidad = models.CharField(max_length=50, choices=Turno.Especialidad.choices)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    intervalo_minutos = models.IntegerField(default=30)
    activo = models.BooleanField(default=True)

    class Meta:
        db_table = "core_horariomedico"


class Notificacion(models.Model):
    destinatario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        db_column="destinatario_id",
    )
    turno = models.ForeignKey(
        Turno,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        db_column="turno_id",
    )
    tipo = models.CharField(max_length=20)
    canal = models.CharField(max_length=30, default="SMS_Y_EMAIL")
    establecimiento = models.CharField(max_length=120)
    especialidad = models.CharField(max_length=50)
    fecha = models.DateField()
    hora = models.TimeField()
    estado_turno = models.CharField(max_length=20, default="RESERVADO")
    enlace_relativo = models.CharField(max_length=120)
    mensaje = models.CharField(max_length=255)
    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "core_notificacion"
        ordering = ["-creada_en"]
