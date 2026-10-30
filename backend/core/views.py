import csv
import hashlib
import io
import json
from datetime import datetime, timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .middleware import get_client_ip
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
from .permissions import (
    IsAdminRole,
    IsAfiliado,
    IsCargoSuperiorAuditoria,
    IsMedico,
    IsRecepcion,
    IsTitularOrAuthorizedDelegate,
    tiene_acceso_beneficiario,
)
from .serializers import (
    AuditLogSerializer,
    CatalogoEstablecimientoSerializer,
    ChangePasswordSerializer,
    DelegacionFamiliarSerializer,
    HorarioMedicoSerializer,
    LoginSerializer,
    NotificacionSerializer,
    RegistroConfirmarOTPSerializer,
    RegistroSolicitarOTPSerializer,
    ReprogramarTurnoSerializer,
    ReservaTurnoSerializer,
    TurnoAfiliadoSerializer,
    TurnoMedicoSerializer,
    TurnoRecepcionSerializer,
    UserProfileSerializer,
    UserSessionSerializer,
    VerifyOTPSerializer,
    validar_politica_clave_robusta,
)
from .services import (
    IESSCircuitBreaker,
    IESSInternalGatewayClient,
    ServicioExternoNoDisponible,
    consultar_padron_afiliacion_iess,
    crear_notificacion_segura,
    generar_otp_seguro,
    validar_afiliacion_iess,
    verificar_otp_seguro,
)

ESTABLECIMIENTOS_DEFAULT = [
    "Hospital Carlos Andrade Marín (HCAM)",
    "Centro de Salud IESS Cotocollao",
    "Hospital del Día El Batán",
]

DUMMY_PASSWORD_HASH = make_password("DummyPasswordTimingMitigation#2026!")


def obtener_establecimientos_activos() -> list[str]:
    nombres = list(
        CatalogoEstablecimiento.objects.filter(activo=True).values_list("nombre", flat=True)
    )
    return nombres if nombres else ESTABLECIMIENTOS_DEFAULT


# =============================================================================
# 0. DISPONIBILIDAD CONTINUA 24/7 SIN VENTANA DE MANTENIMIENTO (REQ. 113)
# =============================================================================


class HealthCheck24x7View(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        db_ok = False
        cache_ok = False
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT 1")
                db_ok = cur.fetchone()[0] == 1
            cache.set("healthcheck_ping", "ok", timeout=10)
            cache_ok = cache.get("healthcheck_ping") == "ok"
        except Exception:
            pass

        healthy = db_ok and cache_ok
        return Response(
            {
                "status": "healthy" if healthy else "degraded",
                "disponibilidad_objetivo": "99.9% (Operación Continua 24/7 - Req. 113)",
                "ventana_mantenimiento_diaria": "ELIMINADA",
                "despliegue": "Rolling Update / Zero-Downtime",
                "postgresql_activo": db_ok,
                "cache_compartida_activa": cache_ok,
                "integracion_gateway": IESSInternalGatewayClient.get_telemetry(),
                "politica_lopdp": {
                    "retencion_maxima_anios": 5,
                    "custodia": "Exclusiva IESS",
                    "entrenamiento_ia_externa": "PROHIBIDO (Req. 114)",
                },
            },
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# =============================================================================
# 1. IDENTIFICACIÓN CONTRA PADRÓN IESS + REGISTRO OTP (REQ. 102)
#    Y AUTENTICACIÓN ROBUSTA MFA + SESIONES VALIDADAS (REQ. 107)
# =============================================================================


class RegistroConsultarCedulaView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        cedula = str(request.data.get("cedula", "")).strip()
        if not es_cedula_ecuatoriana_valida(cedula):
            return Response(
                {
                    "detail": "Número de cédula ecuatoriana inválido (verifique los 10 dígitos, provincia y verificador Módulo 10)."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            datos_iess = consultar_padron_afiliacion_iess(cedula)
        except ServicioExternoNoDisponible as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if datos_iess.get("ya_registrado"):
            return Response(
                {"detail": "La cédula indicada ya posee una cuenta registrada. Inicie sesión."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not datos_iess.get("cobertura_activa"):
            return Response(
                {"detail": "La cédula no registra afiliación activa en el servicio institucional."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response(
            {
                "cedula": datos_iess["cedula"],
                "nombres": datos_iess["nombres"],
                "fecha_nacimiento": datos_iess["fecha_nacimiento"],
                "cobertura_activa": True,
            },
            status=status.HTTP_200_OK,
        )


class RegistroSolicitarOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegistroSolicitarOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cedula = data["cedula"]
        email = data["email"].strip().lower()
        telefono = data["telefono"].strip()
        raw_password = data["password"]

        if User.objects.filter(cedula=cedula).exists():
            return Response(
                {"detail": "Esta cédula ya se encuentra registrada."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"detail": "El correo electrónico ya está asociado a otra cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            padron = consultar_padron_afiliacion_iess(cedula)
        except ServicioExternoNoDisponible as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not padron.get("cobertura_activa") or padron.get("ya_registrado"):
            return Response(
                {"detail": "No fue posible validar la afiliación institucional para el registro."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validar_politica_clave_robusta(
                raw_password, cedula, padron["fecha_nacimiento"]
            )
        except drf_serializers.ValidationError as exc:
            msg = exc.detail[0] if isinstance(exc.detail, list) else str(exc.detail)
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        otp_code = generar_otp_seguro(
            "registro_afiliado",
            cedula,
            ttl_segundos=300,
            extra={
                "cedula": cedula,
                "nombres": padron["nombres"],
                "fecha_nacimiento": padron["fecha_nacimiento"],
                "email": email,
                "telefono": telefono,
                "password_hash": make_password(raw_password),
            },
        )

        return Response(
            {
                "mensaje": "Código OTP enviado para verificar correo electrónico y teléfono móvil.",
                "cedula": cedula,
                "debug_otp": otp_code,
            },
            status=status.HTTP_200_OK,
        )


class RegistroConfirmarOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegistroConfirmarOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cedula = serializer.validated_data["cedula"]
        otp = serializer.validated_data["otp"]

        valido, extra = verificar_otp_seguro(
            "registro_afiliado", cedula, otp, return_extra=True
        )
        if not valido or not extra:
            return Response(
                {"detail": "Código OTP inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(cedula=cedula).exists():
            return Response(
                {"detail": "La cuenta ya fue activada previamente."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fecha_nac = datetime.strptime(extra["fecha_nacimiento"], "%Y-%m-%d").date()
        user = User(
            cedula=extra["cedula"],
            nombres=extra["nombres"],
            fecha_nacimiento=fecha_nac,
            email=extra["email"],
            telefono=extra["telefono"],
            rol=User.Rol.AFILIADO,
            password=extra["password_hash"],
            debe_cambiar_clave=False,
            is_active=True,
        )
        user.save()

        return Response(
            {
                "mensaje": "Cuenta de afiliado verificada y activada exitosamente. Ya puede iniciar sesión.",
                "cedula": user.cedula,
                "nombres": user.nombres,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 15

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cedula = serializer.validated_data["cedula"].strip()
        password = serializer.validated_data["password"]

        client_ip = get_client_ip(request)
        ip_fail_key = f"login_fails_ip:{client_ip}"
        fails_ip = int(cache.get(ip_fail_key, 0))
        if fails_ip >= 15:
            return Response(
                {
                    "detail": "Demasiados intentos de acceso fallidos desde esta dirección IP. Intente más tarde.",
                    "retry_after_seconds": 900,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        user = User.objects.filter(cedula=cedula, is_active=True).first()
        if not user:
            # Mitigación estricta de Timing Attacks (Anti-Enumeración de Cédulas)
            check_password(password, DUMMY_PASSWORD_HASH)
            cache.set(ip_fail_key, fails_ip + 1, timeout=900)
            return Response(
                {"detail": "Credenciales inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        now = timezone.now()

        if user.bloqueado_hasta and user.bloqueado_hasta <= now:
            user.intentos_fallidos = 0
            user.bloqueado_hasta = None
            user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

        if (
            user.intentos_fallidos >= self.MAX_FAILED_ATTEMPTS
            and user.bloqueado_hasta
            and user.bloqueado_hasta > now
        ):
            segundos_restantes = int((user.bloqueado_hasta - now).total_seconds())
            return Response(
                {
                    "detail": "Cuenta bloqueada temporalmente por múltiples intentos fallidos.",
                    "retry_after_seconds": max(segundos_restantes, 1),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        if not user.check_password(password):
            user.intentos_fallidos += 1
            if user.intentos_fallidos >= self.MAX_FAILED_ATTEMPTS:
                user.bloqueado_hasta = now + timedelta(minutes=self.LOCKOUT_MINUTES)
            user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
            cache.set(ip_fail_key, fails_ip + 1, timeout=900)
            return Response(
                {"detail": "Credenciales inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        user.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
        cache.delete(ip_fail_key)

        otp_code = generar_otp_seguro("login", user.cedula, ttl_segundos=300)
        return Response(
            {
                "requires_otp": True,
                "cedula": user.cedula,
                "mensaje": "Ingrese el código de verificación MFA de 6 dígitos.",
                "debug_otp": otp_code,
            },
            status=status.HTTP_200_OK,
        )


class VerifyOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cedula = serializer.validated_data["cedula"].strip()
        otp = serializer.validated_data["otp"].strip()

        user = User.objects.filter(cedula=cedula, is_active=True).first()
        if not user or not verificar_otp_seguro("login", cedula, otp):
            return Response(
                {"detail": "Código OTP inválido o expirado."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        now = timezone.now()
        session = UserSession.objects.create(
            usuario=user,
            ip=get_client_ip(request),
            user_agent=str(request.META.get("HTTP_USER_AGENT", ""))[:255],
            mfa_verificado=True,
            activa=True,
            expira_en=now + timedelta(hours=8),
        )

        refresh = RefreshToken.for_user(user)
        refresh["sid"] = str(session.id)
        refresh["rol"] = user.rol
        refresh["mfa"] = True

        access = refresh.access_token
        access["sid"] = str(session.id)
        access["rol"] = user.rol
        access["mfa"] = True

        session.jti_refresh = str(refresh["jti"])
        session.save(update_fields=["jti_refresh"])

        user.last_login = now
        user.save(update_fields=["last_login"])

        return Response(
            {
                "access": str(access),
                "refresh": str(refresh),
                "session_id": str(session.id),
                "debe_cambiar_clave": user.debe_cambiar_clave,
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class RefreshSessionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_refresh = request.data.get("refresh")
        if not raw_refresh:
            return Response(
                {"detail": "Token refresh requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            refresh = RefreshToken(raw_refresh)
            sid = refresh.get("sid")
            cedula = refresh.get("user_id")
            session = UserSession.objects.get(
                id=sid,
                usuario__cedula=cedula,
                activa=True,
                mfa_verificado=True,
            )
            now = timezone.now()
            if session.expira_en <= now:
                session.activa = False
                session.motivo_cierre = "EXPIRADA"
                session.save(update_fields=["activa", "motivo_cierre"])
                return Response(
                    {"detail": "La sesión ha expirado."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            session.ultima_actividad = now
            session.save(update_fields=["ultima_actividad"])

            access = refresh.access_token
            access["sid"] = str(session.id)
            access["rol"] = session.usuario.rol
            access["mfa"] = True
            return Response({"access": str(access)}, status=status.HTTP_200_OK)
        except (TokenError, UserSession.DoesNotExist, ValueError):
            return Response(
                {"detail": "Sesión o token de refresco inválido."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)

        user: User = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.debe_cambiar_clave = False
        user.save(update_fields=["password", "debe_cambiar_clave"])

        current_session = getattr(request, "user_session", None)
        other_sessions = UserSession.objects.filter(usuario=user, activa=True)
        if current_session:
            other_sessions = other_sessions.exclude(id=current_session.id)
        other_sessions.update(activa=False, motivo_cierre="CAMBIO_CLAVE")

        return Response(
            {
                "mensaje": "Contraseña actualizada exitosamente.",
                "debe_cambiar_clave": False,
            },
            status=status.HTTP_200_OK,
        )


class MeSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session = getattr(request, "user_session", None)
        return Response(
            {
                "user": UserProfileSerializer(request.user).data,
                "session": UserSessionSerializer(
                    session, context={"current_session_id": session.id if session else None}
                ).data
                if session
                else None,
            },
            status=status.HTTP_200_OK,
        )


class ActiveSessionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        current = getattr(request, "user_session", None)
        sesiones = UserSession.objects.filter(usuario=request.user, activa=True).order_by(
            "-ultima_actividad"
        )
        return Response(
            UserSessionSerializer(
                sesiones,
                many=True,
                context={"current_session_id": current.id if current else None},
            ).data,
            status=status.HTTP_200_OK,
        )

    def delete(self, request, session_id=None):
        if not session_id:
            return Response(
                {"detail": "Identificador de sesión requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated = UserSession.objects.filter(
            id=session_id, usuario=request.user, activa=True
        ).update(activa=False, motivo_cierre="REVOCADA_USUARIO")
        if not updated:
            return Response(
                {"detail": "Sesión no encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"mensaje": "Sesión revocada correctamente."}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        cerrar_todas = bool(request.data.get("todas", False))
        if cerrar_todas:
            UserSession.objects.filter(usuario=request.user, activa=True).update(
                activa=False, motivo_cierre="LOGOUT_GLOBAL"
            )
        else:
            session = getattr(request, "user_session", None)
            if session:
                session.activa = False
                session.motivo_cierre = "LOGOUT"
                session.save(update_fields=["activa", "motivo_cierre"])
        return Response({"mensaje": "Sesión cerrada de forma segura."}, status=status.HTTP_200_OK)


# =============================================================================
# 2. GESTIÓN DE TURNOS, DISPONIBILIDAD FUTURA Y CONCURRENCIA (REQ. 101)
# =============================================================================


class DisponibilidadTurnosView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado]

    def get(self, request):
        especialidad = request.query_params.get("especialidad", "").strip()
        establecimiento = request.query_params.get("establecimiento", "").strip()
        fecha_str = request.query_params.get("fecha", "").strip()
        establecimientos_activos = obtener_establecimientos_activos()

        if not especialidad or not establecimiento or not fecha_str:
            return Response(
                {
                    "establecimientos": establecimientos_activos,
                    "especialidades": [c[0] for c in Turno.Especialidad.choices],
                    "horarios_disponibles": [],
                    "grilla_turnos": [],
                },
                status=status.HTTP_200_OK,
            )

        try:
            fecha_obj = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            return Response(
                {"detail": "Formato de fecha inválido. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hoy = timezone.localdate()
        if fecha_obj < hoy:
            return Response(
                {"detail": "No se permite seleccionar ni consultar fechas pasadas."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if fecha_obj > hoy + timedelta(days=365):
            return Response(
                {"detail": "La fecha seleccionada excede el horizonte máximo de programación (1 año)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        horarios = HorarioMedico.objects.filter(
            especialidad=especialidad,
            establecimiento=establecimiento,
            activo=True,
        ).select_related("medico")

        # Turnos activos ocupados por médico (solo estado RESERVADO)
        ocupados_medico = set(
            Turno.objects.filter(
                fecha=fecha_obj,
                medico__in=[h.medico_id for h in horarios],
                estado=Turno.Estado.RESERVADO,
            ).values_list("medico_id", "hora")
        )

        # Turnos activos ocupados en el mismo establecimiento y especialidad
        ocupados_especialidad = set(
            Turno.objects.filter(
                fecha=fecha_obj,
                establecimiento=establecimiento,
                especialidad=especialidad,
                estado=Turno.Estado.RESERVADO,
            ).values_list("hora", flat=True)
        )

        hora_actual_local = timezone.localtime().time()
        disponibles = []
        grilla = []

        for h in horarios:
            cursor = datetime.combine(fecha_obj, h.hora_inicio)
            limite = datetime.combine(fecha_obj, h.hora_fin)
            paso = timedelta(minutes=max(h.intervalo_minutos, 15))
            while cursor < limite:
                hora_slot = cursor.time()
                pasado_hoy = fecha_obj == hoy and hora_slot <= hora_actual_local
                esta_ocupado = (
                    (h.medico_id, hora_slot) in ocupados_medico
                    or hora_slot in ocupados_especialidad
                )
                libre = (not pasado_hoy) and (not esta_ocupado)

                item = {
                    "medico_cedula": h.medico.cedula,
                    "medico_nombre": h.medico.nombres,
                    "establecimiento": h.establecimiento,
                    "especialidad": h.especialidad,
                    "fecha": fecha_str,
                    "hora": hora_slot.strftime("%H:%M"),
                    "disponible": libre,
                    "motivo_no_disponible": (
                        "HORARIO_PASADO" if pasado_hoy else ("RESERVADO" if esta_ocupado else "")
                    ),
                }
                if not pasado_hoy:
                    grilla.append(item)
                if libre:
                    disponibles.append(item)
                cursor += paso

        return Response(
            {
                "establecimiento": establecimiento,
                "especialidad": especialidad,
                "fecha": fecha_str,
                "horarios_disponibles": disponibles,
                "grilla_turnos": grilla,
            },
            status=status.HTTP_200_OK,
        )


class ReservarTurnoView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado, IsTitularOrAuthorizedDelegate]

    def post(self, request):
        serializer = ReservaTurnoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        beneficiario_cedula = (data.get("beneficiario_cedula") or request.user.cedula).strip()

        if not tiene_acceso_beneficiario(request.user, beneficiario_cedula):
            return Response(
                {
                    "detail": "Acceso bloqueado (Anti-BOLA): no cuenta con delegación familiar activa."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        beneficiario = get_object_or_404(
            User, cedula=beneficiario_cedula, rol=User.Rol.AFILIADO, is_active=True
        )
        medico = get_object_or_404(
            User, cedula=data["medico_cedula"], rol=User.Rol.MEDICO, is_active=True
        )

        hoy = timezone.localdate()
        if data["fecha"] < hoy:
            return Response(
                {"detail": "No es posible reservar turnos en fechas pasadas."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if data["fecha"] == hoy and data["hora"] <= timezone.localtime().time():
            return Response(
                {"detail": "El horario seleccionado para el día de hoy ya transcurrió."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            afiliacion = validar_afiliacion_iess(beneficiario.cedula)
        except ServicioExternoNoDisponible as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not afiliacion.get("cobertura_activa"):
            return Response(
                {"detail": "El beneficiario no registra cobertura activa en el IESS."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            with transaction.atomic():
                # 1. Validar límite de 1 turno activo por especialidad para el beneficiario (Req. 101)
                ya_tiene_activo = (
                    Turno.objects.select_for_update()
                    .filter(
                        afiliado=beneficiario,
                        especialidad=data["especialidad"],
                        estado=Turno.Estado.RESERVADO,
                    )
                    .exists()
                )
                if ya_tiene_activo:
                    return Response(
                        {
                            "detail": (
                                f"El afiliado ya mantiene un turno activo en {data['especialidad']} (máximo 1 por especialidad)."
                            )
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # 2. Bloqueo atómico contra doble reserva concurrente en mismo establecimiento, especialidad o médico
                ya_ocupado = (
                    Turno.objects.select_for_update()
                    .filter(
                        Q(medico=medico)
                        | Q(
                            establecimiento=data["establecimiento"],
                            especialidad=data["especialidad"],
                        ),
                        fecha=data["fecha"],
                        hora=data["hora"],
                        estado=Turno.Estado.RESERVADO,
                    )
                    .exists()
                )
                if ya_ocupado:
                    return Response(
                        {
                            "detail": "El turno seleccionado para este establecimiento, especialidad y horario ya fue reservado por otro usuario."
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                turno = Turno.objects.create(
                    afiliado=beneficiario,
                    reservado_por=request.user,
                    medico=medico,
                    establecimiento=data["establecimiento"],
                    especialidad=data["especialidad"],
                    fecha=data["fecha"],
                    hora=data["hora"],
                    estado=Turno.Estado.RESERVADO,
                )
                notificacion = crear_notificacion_segura(request.user, turno, "RESERVA")
        except IntegrityError:
            return Response(
                {"detail": "El horario seleccionado ya fue ocupado por otra solicitud simultánea."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                "turno": TurnoAfiliadoSerializer(turno).data,
                "notificacion": NotificacionSerializer(notificacion).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MisTurnosView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado, IsTitularOrAuthorizedDelegate]

    def get(self, request):
        beneficiario_cedula = (
            request.query_params.get("beneficiario_cedula") or request.user.cedula
        ).strip()

        if not es_cedula_ecuatoriana_valida(beneficiario_cedula):
            return Response(
                {"detail": "Número de cédula ecuatoriana inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not tiene_acceso_beneficiario(request.user, beneficiario_cedula):
            return Response(
                {"detail": "No tiene autorización para consultar turnos de esta cédula."},
                status=status.HTTP_403_FORBIDDEN,
            )

        turnos = (
            Turno.objects.filter(afiliado__cedula=beneficiario_cedula)
            .select_related("afiliado", "medico")
            .order_by("fecha", "hora")
        )
        return Response(TurnoAfiliadoSerializer(turnos, many=True).data, status=status.HTTP_200_OK)


class TurnoDetalleView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado, IsTitularOrAuthorizedDelegate]

    def get(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado", "medico"), pk=pk)
        self.check_object_permissions(request, turno)
        return Response(TurnoAfiliadoSerializer(turno).data, status=status.HTTP_200_OK)


def _cumple_anticipacion_24h(fecha, hora) -> bool:
    cita_naive = datetime.combine(fecha, hora)
    cita_dt = timezone.make_aware(cita_naive, timezone.get_current_timezone())
    return (cita_dt - timezone.now()) >= timedelta(hours=24)


class CancelarTurnoView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado, IsTitularOrAuthorizedDelegate]

    def post(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado", "medico"), pk=pk)
        self.check_object_permissions(request, turno)

        if turno.estado != Turno.Estado.RESERVADO:
            return Response(
                {"detail": "Solo se pueden cancelar turnos en estado RESERVADO."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _cumple_anticipacion_24h(turno.fecha, turno.hora):
            return Response(
                {"detail": "La cancelación requiere al menos 24 horas de anticipación."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            turno.estado = Turno.Estado.CANCELADO
            turno.save(update_fields=["estado"])
            notificacion = crear_notificacion_segura(request.user, turno, "CANCELACION")

        return Response(
            {
                "turno": TurnoAfiliadoSerializer(turno).data,
                "notificacion": NotificacionSerializer(notificacion).data,
            },
            status=status.HTTP_200_OK,
        )


class ReprogramarTurnoView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado, IsTitularOrAuthorizedDelegate]

    def post(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado", "medico"), pk=pk)
        self.check_object_permissions(request, turno)

        if turno.estado != Turno.Estado.RESERVADO:
            return Response(
                {"detail": "Solo se pueden reprogramar turnos en estado RESERVADO."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not _cumple_anticipacion_24h(turno.fecha, turno.hora):
            return Response(
                {"detail": "La reprogramación requiere al menos 24 horas de anticipación."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ReprogramarTurnoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nueva_fecha = serializer.validated_data["fecha"]
        nueva_hora = serializer.validated_data["hora"]
        medico_cedula = serializer.validated_data.get("medico_cedula")

        if not _cumple_anticipacion_24h(nueva_fecha, nueva_hora):
            return Response(
                {"detail": "El nuevo horario debe programarse con al menos 24 horas de anticipación."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nuevo_medico = turno.medico
        if medico_cedula:
            nuevo_medico = get_object_or_404(
                User, cedula=medico_cedula, rol=User.Rol.MEDICO, is_active=True
            )

        try:
            with transaction.atomic():
                # Validar atómicamente contra doble reserva en nuevo horario
                ya_ocupado = (
                    Turno.objects.select_for_update()
                    .filter(
                        Q(medico=nuevo_medico)
                        | Q(
                            establecimiento=turno.establecimiento,
                            especialidad=turno.especialidad,
                        ),
                        fecha=nueva_fecha,
                        hora=nueva_hora,
                        estado=Turno.Estado.RESERVADO,
                    )
                    .exclude(id=turno.id)
                    .exists()
                )
                if ya_ocupado:
                    return Response(
                        {
                            "detail": "El nuevo horario seleccionado ya fue reservado por otra solicitud."
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                turno.fecha = nueva_fecha
                turno.hora = nueva_hora
                turno.medico = nuevo_medico
                turno.save(update_fields=["fecha", "hora", "medico"])
                notificacion = crear_notificacion_segura(request.user, turno, "REPROGRAMACION")
        except IntegrityError:
            return Response(
                {"detail": "El nuevo horario seleccionado ya no se encuentra disponible."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            {
                "turno": TurnoAfiliadoSerializer(turno).data,
                "notificacion": NotificacionSerializer(notificacion).data,
            },
            status=status.HTTP_200_OK,
        )


class MisNotificacionesView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado]

    def get(self, request):
        notificaciones = Notificacion.objects.filter(destinatario=request.user)[:30]
        return Response(
            NotificacionSerializer(notificaciones, many=True).data,
            status=status.HTTP_200_OK,
        )


# =============================================================================
# 3. DELEGACIÓN FAMILIAR CON VERIFICACIÓN OTP (ANTI-BOLA - REQ. 106)
# =============================================================================


class DelegacionesListView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado]

    def get(self, request):
        vinculos = (
            DelegacionFamiliar.objects.filter(
                Q(
                    titular=request.user,
                    tipo_vinculo=DelegacionFamiliar.TipoVinculo.HIJO_MENOR,
                    activo=True,
                )
                | Q(
                    delegado=request.user,
                    tipo_vinculo=DelegacionFamiliar.TipoVinculo.ADULTO_AUTORIZADO,
                    activo=True,
                )
            )
            .select_related("titular", "delegado")
            .order_by("tipo_vinculo")
        )
        return Response(
            DelegacionFamiliarSerializer(
                vinculos, many=True, context={"actor": request.user}
            ).data,
            status=status.HTTP_200_OK,
        )


class SolicitarDelegacionView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado]

    def post(self, request):
        titular_cedula = str(request.data.get("titular_cedula", "")).strip()
        if not es_cedula_ecuatoriana_valida(titular_cedula) or titular_cedula == request.user.cedula:
            return Response(
                {
                    "detail": "Ingrese un número de cédula ecuatoriana válido correspondiente a otro afiliado titular adulto."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        titular = User.objects.filter(
            cedula=titular_cedula, rol=User.Rol.AFILIADO, is_active=True
        ).first()
        if not titular:
            return Response(
                {"detail": "No se encontró un afiliado activo con la cédula indicada."},
                status=status.HTTP_404_NOT_FOUND,
            )

        otp_code = generar_otp_seguro(
            "delegacion", f"{titular.cedula}:{request.user.cedula}", ttl_segundos=300
        )
        return Response(
            {
                "mensaje": (
                    "Se envió un código OTP de autorización al teléfono/correo del familiar titular."
                ),
                "titular_cedula": titular.cedula,
                "debug_otp": otp_code,
            },
            status=status.HTTP_200_OK,
        )


class ConfirmarDelegacionOTPView(APIView):
    permission_classes = [IsAuthenticated, IsAfiliado]

    def post(self, request):
        titular_cedula = str(request.data.get("titular_cedula", "")).strip()
        otp = str(request.data.get("otp", "")).strip()

        if not es_cedula_ecuatoriana_valida(titular_cedula) or not otp:
            return Response(
                {"detail": "Cédula ecuatoriana válida del titular y código OTP son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        titular = User.objects.filter(
            cedula=titular_cedula, rol=User.Rol.AFILIADO, is_active=True
        ).first()
        if not titular or not verificar_otp_seguro(
            "delegacion", f"{titular.cedula}:{request.user.cedula}", otp
        ):
            return Response(
                {"detail": "Código OTP de delegación inválido o expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delegacion, _ = DelegacionFamiliar.objects.update_or_create(
            titular=titular,
            delegado=request.user,
            defaults={
                "tipo_vinculo": DelegacionFamiliar.TipoVinculo.ADULTO_AUTORIZADO,
                "activo": True,
            },
        )
        return Response(
            {
                "mensaje": "Delegación familiar autorizada correctamente.",
                "delegacion": DelegacionFamiliarSerializer(
                    delegacion, context={"actor": request.user}
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# 4. ENDPOINTS SEGREGADOS POR ROL DE FUNCIONARIO (RBAC/ABAC - REQ. 108)
#    Y EXTRACCIÓN DE LOGS/AUDITORÍAS PARA CARGOS SUPERIORES
# =============================================================================


class StaffRecepcionView(APIView):
    """
    Req. 108: Recepción solo consulta turnos del día actual en su establecimiento,
    con correo y teléfono enmascarados y sin acceso a agendas globales ni datos clínicos.
    """

    permission_classes = [IsAuthenticated, IsRecepcion]

    def get(self, request):
        cedula = str(request.query_params.get("cedula", "")).strip()
        if not es_cedula_ecuatoriana_valida(cedula):
            return Response(
                {
                    "detail": "Ingrese un número de cédula ecuatoriana válido (Módulo 10) para consultar el check-in de hoy."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        hoy = timezone.localdate()
        qs = Turno.objects.filter(afiliado__cedula=cedula, fecha=hoy)
        if request.user.establecimiento_asignado:
            qs = qs.filter(establecimiento=request.user.establecimiento_asignado)

        turnos = qs.select_related("afiliado", "medico").order_by("hora")
        return Response(
            TurnoRecepcionSerializer(turnos, many=True).data,
            status=status.HTTP_200_OK,
        )


class StaffRecepcionConfirmarAsistenciaView(APIView):
    """Permite a Recepción confirmar asistencia de turnos del día actual en su establecimiento."""

    permission_classes = [IsAuthenticated, IsRecepcion]

    def post(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado", "medico"), pk=pk)
        if turno.fecha != timezone.localdate():
            return Response(
                {"detail": "Solo se puede confirmar asistencia de turnos correspondientes a hoy."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            request.user.establecimiento_asignado
            and turno.establecimiento != request.user.establecimiento_asignado
        ):
            return Response(
                {"detail": "Acceso denegado: el turno pertenece a otro establecimiento."},
                status=status.HTTP_403_FORBIDDEN,
            )

        turno.asistencia_confirmada = True
        turno.save(update_fields=["asistencia_confirmada"])
        return Response(TurnoRecepcionSerializer(turno).data, status=status.HTTP_200_OK)


class StaffAgendaMedicaView(APIView):
    permission_classes = [IsAuthenticated, IsMedico]

    def get(self, request):
        for param in ("medico_cedula", "medico_id", "medico"):
            solicitado = request.query_params.get(param)
            if solicitado:
                ced_solicitada = str(solicitado).strip()
                if not es_cedula_ecuatoriana_valida(ced_solicitada):
                    return Response(
                        {"detail": "Número de cédula ecuatoriana inválido."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if ced_solicitada != request.user.cedula:
                    return Response(
                        {"detail": "Acceso denegado: no puede consultar la agenda de otro médico."},
                        status=status.HTTP_403_FORBIDDEN,
                    )

        hoy = timezone.localdate()
        turnos = (
            Turno.objects.filter(medico=request.user, fecha=hoy)
            .select_related("afiliado")
            .order_by("hora")
        )
        return Response(
            TurnoMedicoSerializer(turnos, many=True).data,
            status=status.HTTP_200_OK,
        )


class StaffMedicoAtenderView(APIView):
    permission_classes = [IsAuthenticated, IsMedico]

    def get(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado"), pk=pk)
        if turno.medico_id != request.user.cedula:
            return Response(
                {"detail": "Acceso denegado: el turno pertenece a otro profesional médico."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(TurnoMedicoSerializer(turno).data, status=status.HTTP_200_OK)

    def post(self, request, pk: int):
        turno = get_object_or_404(Turno.objects.select_related("afiliado"), pk=pk)
        if turno.medico_id != request.user.cedula:
            return Response(
                {"detail": "Acceso denegado: no puede modificar turnos de otro médico."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if turno.fecha != timezone.localdate():
            return Response(
                {"detail": "Solo se pueden marcar como atendidos los turnos del día actual."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        turno.estado = Turno.Estado.ATENDIDO
        turno.save(update_fields=["estado"])
        return Response(TurnoMedicoSerializer(turno).data, status=status.HTTP_200_OK)


def _filtrar_audit_logs(request):
    qs = AuditLog.objects.all().order_by("-timestamp")
    metodo = request.query_params.get("metodo")
    rol = request.query_params.get("rol")
    status_code = request.query_params.get("status_code")
    ruta = request.query_params.get("ruta")

    if metodo:
        qs = qs.filter(metodo=metodo.upper())
    if rol:
        qs = qs.filter(rol=rol.upper())
    if status_code and str(status_code).isdigit():
        qs = qs.filter(status_code=int(status_code))
    if ruta:
        qs = qs.filter(ruta__icontains=ruta)
    return qs


class StaffAuditLogsView(APIView):
    permission_classes = [IsAuthenticated, IsCargoSuperiorAuditoria]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 80)), 500)
        logs_qs = _filtrar_audit_logs(request)[:limit]

        total_eventos = AuditLog.objects.count()
        eventos_seguridad = AuditLog.objects.filter(
            status_code__in=[401, 403, 429]
        ).count()
        sesiones_activas = UserSession.objects.filter(
            activa=True, expira_en__gt=timezone.now()
        ).count()

        return Response(
            {
                "metricas": {
                    "total_eventos_auditados": total_eventos,
                    "intentos_bloqueados_401_403_429": eventos_seguridad,
                    "sesiones_activas_validadas": sesiones_activas,
                    "circuit_breaker": IESSCircuitBreaker.get_status(),
                    "gateway_integracion": IESSInternalGatewayClient.get_telemetry(),
                    "disponibilidad": "24/7 Continua (Sin ventana de mantenimiento)",
                    "retencion_lopdp": "5 años máx. · Custodia exclusiva IESS · IA externa prohibida",
                },
                "logs": AuditLogSerializer(logs_qs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class StaffAuditExportView(APIView):
    """
    Permite a cargos superiores (ADMIN y SOPORTE) extraer los logs y auditorías
    sanitizadas del sistema en formato CSV o JSON con huella SHA-256 de integridad.
    """

    permission_classes = [IsAuthenticated, IsCargoSuperiorAuditoria]

    def get(self, request):
        formato = request.query_params.get("formato", "csv").lower()
        tipo = request.query_params.get("tipo", "auditoria").lower()
        timestamp_tag = timezone.localtime().strftime("%Y%m%d_%H%M%S")

        if tipo == "sesiones":
            sesiones = UserSession.objects.select_related("usuario").order_by(
                "-creada_en"
            )[:500]
            registros = [
                {
                    "session_id": str(s.id),
                    "usuario_rol": s.usuario.rol,
                    "usuario_ref": f"HASH-{hashlib.sha256(s.usuario.cedula.encode()).hexdigest()[:10]}",
                    "ip": s.ip or "",
                    "mfa_verificado": s.mfa_verificado,
                    "activa": s.activa,
                    "creada_en": s.creada_en.isoformat(),
                    "ultima_actividad": s.ultima_actividad.isoformat(),
                    "expira_en": s.expira_en.isoformat(),
                    "motivo_cierre": s.motivo_cierre,
                }
                for s in sesiones
            ]
        else:
            logs = _filtrar_audit_logs(request)[:1000]
            registros = []
            for log in logs:
                cedula_val = log.usuario_cedula or "ANONIMO"
                if log.rol == User.Rol.AFILIADO and cedula_val != "ANONIMO":
                    cedula_val = (
                        cedula_val
                        if request.user.rol == User.Rol.SOPORTE
                        else f"ANON-{hashlib.sha256(cedula_val.encode()).hexdigest()[:8]}"
                    )
                registros.append(
                    {
                        "id": log.id,
                        "timestamp": log.timestamp.isoformat(),
                        "usuario_ref": cedula_val,
                        "rol": log.rol or "N/A",
                        "ip": log.ip or "",
                        "metodo": log.metodo,
                        "ruta": log.ruta,
                        "status_code": log.status_code,
                        "payload_sanitizado": log.payload_sanitizado,
                    }
                )

        if formato == "json":
            reporte = {
                "generado_en": timezone.localtime().isoformat(),
                "extraido_por_rol": request.user.rol,
                "tipo_reporte": tipo,
                "total_registros": len(registros),
                "registros": registros,
            }
            contenido_bytes = json.dumps(reporte, ensure_ascii=False, indent=2).encode("utf-8")
            sha256_hex = hashlib.sha256(contenido_bytes).hexdigest()
            resp = HttpResponse(contenido_bytes, content_type="application/json; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="iess_{tipo}_{timestamp_tag}.json"'
            resp["X-Audit-SHA256"] = sha256_hex
            return resp

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        if tipo == "sesiones":
            writer.writerow(
                [
                    "session_id",
                    "usuario_rol",
                    "usuario_ref",
                    "ip",
                    "mfa_verificado",
                    "activa",
                    "creada_en",
                    "ultima_actividad",
                    "expira_en",
                    "motivo_cierre",
                ]
            )
            for r in registros:
                writer.writerow(
                    [
                        r["session_id"],
                        r["usuario_rol"],
                        r["usuario_ref"],
                        r["ip"],
                        r["mfa_verificado"],
                        r["activa"],
                        r["creada_en"],
                        r["ultima_actividad"],
                        r["expira_en"],
                        r["motivo_cierre"],
                    ]
                )
        else:
            writer.writerow(
                [
                    "id",
                    "timestamp",
                    "usuario_ref",
                    "rol",
                    "ip",
                    "metodo",
                    "ruta",
                    "status_code",
                    "payload_sanitizado",
                ]
            )
            for r in registros:
                writer.writerow(
                    [
                        r["id"],
                        r["timestamp"],
                        r["usuario_ref"],
                        r["rol"],
                        r["ip"],
                        r["metodo"],
                        r["ruta"],
                        r["status_code"],
                        json.dumps(r["payload_sanitizado"], ensure_ascii=False),
                    ]
                )

        contenido_bytes = buffer.getvalue().encode("utf-8")
        sha256_hex = hashlib.sha256(contenido_bytes).hexdigest()
        resp = HttpResponse(contenido_bytes, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="iess_{tipo}_{timestamp_tag}.csv"'
        resp["X-Audit-SHA256"] = sha256_hex
        return resp


class StaffAdminEstadisticasView(APIView):
    """
    Estadísticas 100% agregadas y anonimizadas para rol ADMIN (Req. 108, LOPDP).
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        agregado = (
            Turno.objects.values("especialidad")
            .annotate(
                total=Count("id"),
                reservados=Count("id", filter=Q(estado=Turno.Estado.RESERVADO)),
                atendidos=Count("id", filter=Q(estado=Turno.Estado.ATENDIDO)),
                cancelados=Count("id", filter=Q(estado=Turno.Estado.CANCELADO)),
            )
            .order_by("especialidad")
        )

        mapa = {item["especialidad"]: item for item in agregado}
        tarjetas = []
        for esp_val, _ in Turno.Especialidad.choices:
            tarjetas.append(
                mapa.get(
                    esp_val,
                    {
                        "especialidad": esp_val,
                        "total": 0,
                        "reservados": 0,
                        "atendidos": 0,
                        "cancelados": 0,
                    },
                )
            )

        sesiones_activas = UserSession.objects.filter(
            activa=True, expira_en__gt=timezone.now()
        ).count()

        return Response(
            {
                "resumen_especialidades": tarjetas,
                "sesiones_activas_sistema": sesiones_activas,
                "total_eventos_auditoria": AuditLog.objects.count(),
                "retencion_lopdp_anios": 5,
            },
            status=status.HTTP_200_OK,
        )


class StaffAdminHorariosView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        horarios = HorarioMedico.objects.select_related("medico").order_by(
            "establecimiento", "especialidad", "hora_inicio"
        )
        medicos = User.objects.filter(rol=User.Rol.MEDICO, is_active=True).values(
            "cedula", "nombres"
        )
        catalogo = CatalogoEstablecimiento.objects.all()
        return Response(
            {
                "horarios": HorarioMedicoSerializer(horarios, many=True).data,
                "medicos": list(medicos),
                "establecimientos": obtener_establecimientos_activos(),
                "catalogo_establecimientos": CatalogoEstablecimientoSerializer(
                    catalogo, many=True
                ).data,
                "especialidades": [c[0] for c in Turno.Especialidad.choices],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = HorarioMedicoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        horario = serializer.save()
        return Response(
            HorarioMedicoSerializer(horario).data,
            status=status.HTTP_201_CREATED,
        )


class StaffAdminCatalogoView(APIView):
    """Permite al rol ADMIN gestionar el catálogo de establecimientos habilitados (Req. 108)."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request):
        serializer = CatalogoEstablecimientoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        est = serializer.save()
        return Response(
            CatalogoEstablecimientoSerializer(est).data,
            status=status.HTTP_201_CREATED,
        )
