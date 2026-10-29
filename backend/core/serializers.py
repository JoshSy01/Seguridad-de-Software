from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework import serializers

from .models import (
    AuditLog,
    CatalogoEstablecimiento,
    DelegacionFamiliar,
    HorarioMedico,
    Notificacion,
    Turno,
    User,
    UserSession,
    es_cedula_ecuatoriana_valida,
)


class CedulaEcuatorianaField(serializers.CharField):
    """
    Campo de validación estricta para Cédula de Identidad Ecuatoriana (Módulo 10).
    Rechaza cualquier entrada no numérica, fuera de rango provincial o con dígito verificador inválido.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        val = super().to_internal_value(data)
        if val == "" and self.allow_blank:
            return ""
        ced = str(val).strip()
        if not es_cedula_ecuatoriana_valida(ced):
            raise serializers.ValidationError(
                "Número de cédula ecuatoriana inválido (verifique los 10 dígitos, provincia y verificador Módulo 10)."
            )
        return ced


def mask_email(email: str) -> str:
    """Enmascara correo estilo `j***@mail.com` (Req. 108)."""
    if not email or "@" not in email:
        return "***@***"
    local, domain = email.split("@", 1)
    first_char = local[0] if local else "*"
    return f"{first_char}***@{domain}"


def mask_phone(phone: str) -> str:
    """Enmascara teléfono estilo `099***1234` (Req. 108)."""
    digits = (phone or "").strip()
    if len(digits) < 7:
        return "***"
    return f"{digits[:3]}***{digits[-4:]}"


def validar_politica_clave_robusta(password: str, cedula: str, fecha_nacimiento) -> None:
    """
    Validador estricto Req. 107:
    - Mínimo 12 caracteres.
    - Prohibido incluir cédula.
    - Prohibido incluir fecha de nacimiento en ningún formato.
    """
    if len(password) < 12:
        raise serializers.ValidationError(
            "La contraseña debe tener al menos 12 caracteres."
        )

    if cedula and str(cedula) in password:
        raise serializers.ValidationError(
            "La contraseña no puede contener su número de cédula."
        )

    if fecha_nacimiento:
        if isinstance(fecha_nacimiento, str):
            fecha_nacimiento = datetime.strptime(fecha_nacimiento, "%Y-%m-%d").date()
        patrones_fecha = (
            fecha_nacimiento.strftime("%Y%m%d"),
            fecha_nacimiento.strftime("%d%m%Y"),
            fecha_nacimiento.strftime("%Y-%m-%d"),
            fecha_nacimiento.strftime("%d-%m-%Y"),
            fecha_nacimiento.strftime("%Y/%m/%d"),
            fecha_nacimiento.strftime("%d/%m/%Y"),
        )
        for patron in patrones_fecha:
            if patron in password:
                raise serializers.ValidationError(
                    "Por seguridad, la contraseña no puede contener su fecha de nacimiento."
                )


class LoginSerializer(serializers.Serializer):
    cedula = CedulaEcuatorianaField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class VerifyOTPSerializer(serializers.Serializer):
    cedula = CedulaEcuatorianaField()
    otp = serializers.CharField(min_length=6, max_length=6)


class RegistroSolicitarOTPSerializer(serializers.Serializer):
    cedula = CedulaEcuatorianaField()
    email = serializers.EmailField()
    telefono = serializers.RegexField(r"^\d{9,15}$", max_length=15)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class RegistroConfirmarOTPSerializer(serializers.Serializer):
    cedula = CedulaEcuatorianaField()
    otp = serializers.CharField(min_length=6, max_length=6)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        required=False, allow_blank=True, write_only=True, trim_whitespace=False
    )
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user: User = self.context["user"]
        new_password = attrs.get("new_password", "")
        current_password = attrs.get("current_password")

        if current_password:
            if not user.check_password(current_password):
                raise serializers.ValidationError(
                    {"current_password": "La contraseña actual es incorrecta."}
                )

        try:
            validar_politica_clave_robusta(new_password, user.cedula, user.fecha_nacimiento)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.detail})

        if user.check_password(new_password):
            raise serializers.ValidationError(
                {"new_password": "La nueva contraseña debe ser diferente a la actual."}
            )

        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "cedula",
            "nombres",
            "rol",
            "establecimiento_asignado",
            "debe_cambiar_clave",
            "fecha_nacimiento",
        ]


class CatalogoEstablecimientoSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogoEstablecimiento
        fields = ["id", "nombre", "ciudad", "activo"]


class ReservaTurnoSerializer(serializers.Serializer):
    beneficiario_cedula = CedulaEcuatorianaField(required=False, allow_blank=True)
    medico_cedula = CedulaEcuatorianaField()
    establecimiento = serializers.CharField(max_length=120)
    especialidad = serializers.ChoiceField(choices=Turno.Especialidad.choices)
    fecha = serializers.DateField()
    hora = serializers.TimeField()


class ReprogramarTurnoSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    hora = serializers.TimeField()
    medico_cedula = CedulaEcuatorianaField(required=False, allow_blank=True)


class TurnoAfiliadoSerializer(serializers.ModelSerializer):
    afiliado_cedula = serializers.CharField(source="afiliado.cedula", read_only=True)
    afiliado_nombre = serializers.CharField(source="afiliado.nombres", read_only=True)
    medico_cedula = serializers.CharField(source="medico.cedula", read_only=True)
    medico_nombre = serializers.CharField(source="medico.nombres", read_only=True)
    hora = serializers.TimeField(format="%H:%M", read_only=True)
    puede_modificar_24h = serializers.SerializerMethodField()

    class Meta:
        model = Turno
        fields = [
            "id",
            "afiliado_cedula",
            "afiliado_nombre",
            "medico_cedula",
            "medico_nombre",
            "establecimiento",
            "especialidad",
            "fecha",
            "hora",
            "estado",
            "puede_modificar_24h",
        ]

    def get_puede_modificar_24h(self, obj) -> bool:
        if obj.estado != Turno.Estado.RESERVADO:
            return False
        cita_dt = timezone.make_aware(
            datetime.combine(obj.fecha, obj.hora), timezone.get_current_timezone()
        )
        return (cita_dt - timezone.now()) >= timedelta(hours=24)


class TurnoRecepcionSerializer(serializers.ModelSerializer):
    afiliado_cedula = serializers.CharField(source="afiliado.cedula", read_only=True)
    afiliado_nombre = serializers.CharField(source="afiliado.nombres", read_only=True)
    medico_nombre = serializers.CharField(source="medico.nombres", read_only=True)
    email_enmascarado = serializers.SerializerMethodField()
    telefono_enmascarado = serializers.SerializerMethodField()
    hora = serializers.TimeField(format="%H:%M", read_only=True)

    class Meta:
        model = Turno
        fields = [
            "id",
            "afiliado_cedula",
            "afiliado_nombre",
            "email_enmascarado",
            "telefono_enmascarado",
            "medico_nombre",
            "establecimiento",
            "especialidad",
            "fecha",
            "hora",
            "estado",
            "asistencia_confirmada",
        ]

    def get_email_enmascarado(self, obj) -> str:
        return mask_email(obj.afiliado.email)

    def get_telefono_enmascarado(self, obj) -> str:
        return mask_phone(obj.afiliado.telefono)


class TurnoMedicoSerializer(serializers.ModelSerializer):
    afiliado_cedula = serializers.CharField(source="afiliado.cedula", read_only=True)
    afiliado_nombre = serializers.CharField(source="afiliado.nombres", read_only=True)
    hora = serializers.TimeField(format="%H:%M", read_only=True)

    class Meta:
        model = Turno
        fields = [
            "id",
            "afiliado_cedula",
            "afiliado_nombre",
            "establecimiento",
            "especialidad",
            "fecha",
            "hora",
            "estado",
            "asistencia_confirmada",
        ]


class NotificacionSerializer(serializers.ModelSerializer):
    hora = serializers.TimeField(format="%H:%M", read_only=True)

    class Meta:
        model = Notificacion
        fields = [
            "id",
            "tipo",
            "canal",
            "establecimiento",
            "especialidad",
            "fecha",
            "hora",
            "estado_turno",
            "enlace_relativo",
            "mensaje",
            "creada_en",
        ]


class DelegacionFamiliarSerializer(serializers.ModelSerializer):
    beneficiario_cedula = serializers.SerializerMethodField()
    beneficiario_nombre = serializers.SerializerMethodField()

    class Meta:
        model = DelegacionFamiliar
        fields = [
            "id",
            "beneficiario_cedula",
            "beneficiario_nombre",
            "tipo_vinculo",
            "activo",
            "creado_en",
        ]

    def get_beneficiario_cedula(self, obj) -> str:
        actor = self.context.get("actor")
        if (
            obj.tipo_vinculo == DelegacionFamiliar.TipoVinculo.HIJO_MENOR
            and actor
            and obj.titular_id == actor.cedula
        ):
            return obj.delegado.cedula
        return obj.titular.cedula

    def get_beneficiario_nombre(self, obj) -> str:
        actor = self.context.get("actor")
        if (
            obj.tipo_vinculo == DelegacionFamiliar.TipoVinculo.HIJO_MENOR
            and actor
            and obj.titular_id == actor.cedula
        ):
            return obj.delegado.nombres
        return obj.titular.nombres


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "usuario_cedula",
            "rol",
            "ip",
            "metodo",
            "ruta",
            "payload_sanitizado",
            "status_code",
        ]


class UserSessionSerializer(serializers.ModelSerializer):
    es_actual = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            "id",
            "ip",
            "user_agent",
            "mfa_verificado",
            "activa",
            "creada_en",
            "ultima_actividad",
            "expira_en",
            "es_actual",
        ]

    def get_es_actual(self, obj) -> bool:
        current = self.context.get("current_session_id")
        return bool(current and str(obj.id) == str(current))


class HorarioMedicoSerializer(serializers.ModelSerializer):
    medico_cedula = CedulaEcuatorianaField(source="medico.cedula")
    medico_nombre = serializers.CharField(source="medico.nombres", read_only=True)
    hora_inicio = serializers.TimeField(format="%H:%M")
    hora_fin = serializers.TimeField(format="%H:%M")

    class Meta:
        model = HorarioMedico
        fields = [
            "id",
            "medico_cedula",
            "medico_nombre",
            "establecimiento",
            "especialidad",
            "hora_inicio",
            "hora_fin",
            "intervalo_minutos",
            "activo",
        ]

    def create(self, validated_data):
        medico_data = validated_data.pop("medico")
        medico = User.objects.filter(cedula=medico_data["cedula"], rol=User.Rol.MEDICO).first()
        if not medico:
            raise serializers.ValidationError({"medico_cedula": "Médico no encontrado."})
        return HorarioMedico.objects.create(medico=medico, **validated_data)
