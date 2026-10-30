from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import (
    DelegacionFamiliar,
    Turno,
    User,
    UserSession,
    es_cedula_ecuatoriana_valida,
)


class SessionValidatedJWTAuthentication(JWTAuthentication):
    """
    Autenticación JWT respaldada por validación stateful de sesión activa en BD.
    Verifica MFA completado, vigencia absoluta, inactividad máxima (30 min) y no revocación.
    """

    INACTIVITY_LIMIT = timedelta(minutes=30)

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, validated_token = result
        session_id = validated_token.get("sid")
        mfa_ok = validated_token.get("mfa", False)
        token_rol = validated_token.get("rol")

        if not session_id or not mfa_ok:
            raise AuthenticationFailed("Sesión inválida o factor MFA no verificado.")

        if token_rol and token_rol != user.rol:
            raise AuthenticationFailed("Inconsistencia en el rol del token (detección de escalamiento de privilegios).")

        try:
            session = UserSession.objects.get(
                id=session_id,
                usuario=user,
                activa=True,
                mfa_verificado=True,
            )
        except (UserSession.DoesNotExist, ValueError):
            raise AuthenticationFailed("La sesión fue cerrada, revocada o no es válida.")

        now = timezone.now()
        if session.expira_en <= now or (now - session.ultima_actividad) > self.INACTIVITY_LIMIT:
            session.activa = False
            session.motivo_cierre = "EXPIRADA"
            session.save(update_fields=["activa", "motivo_cierre"])
            raise AuthenticationFailed("La sesión ha expirado. Inicie sesión nuevamente.")

        UserSession.objects.filter(id=session.id).update(ultima_actividad=now)
        session.ultima_actividad = now
        request.user_session = session
        return (user, validated_token)


def tiene_acceso_beneficiario(actor: User, beneficiario_cedula: str) -> bool:
    """
    Verifica regla ABAC Anti-BOLA (Req. 106):
    Solo el propio titular o un familiar con vínculo activo en DelegacionFamiliar puede operar.
    """
    if not actor or not actor.is_authenticated:
        return False
    if not beneficiario_cedula or str(beneficiario_cedula) == str(actor.cedula):
        return True

    return DelegacionFamiliar.objects.filter(
        Q(delegado=actor, titular__cedula=beneficiario_cedula, activo=True)
        | Q(
            titular=actor,
            delegado__cedula=beneficiario_cedula,
            tipo_vinculo=DelegacionFamiliar.TipoVinculo.HIJO_MENOR,
            activo=True,
        )
    ).exists()


class IsPasswordUpdated(BasePermission):
    message = "Debe cambiar su contraseña temporal obligatoria antes de ejecutar acciones en el sistema."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and not request.user.debe_cambiar_clave
        )


class IsAfiliado(BasePermission):
    message = "Acceso restringido exclusivamente a usuarios con rol AFILIADO."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == User.Rol.AFILIADO
            and not request.user.debe_cambiar_clave
        )


class IsRecepcion(BasePermission):
    message = "Acceso restringido exclusivamente al personal de RECEPCION."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == User.Rol.RECEPCION
            and not request.user.debe_cambiar_clave
        )


class IsMedico(BasePermission):
    message = "Acceso restringido exclusivamente al personal MEDICO."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == User.Rol.MEDICO
            and not request.user.debe_cambiar_clave
        )


class IsSoporte(BasePermission):
    message = "Acceso restringido exclusivamente al personal de SOPORTE."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == User.Rol.SOPORTE
            and not request.user.debe_cambiar_clave
        )


class IsAdminRole(BasePermission):
    message = "Acceso restringido exclusivamente al rol ADMIN."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol == User.Rol.ADMIN
            and not request.user.debe_cambiar_clave
        )


class IsCargoSuperiorAuditoria(BasePermission):
    """Permite consultar y extraer auditorías/logs a cargos autorizados (SOPORTE y ADMIN)."""

    message = "Acceso denegado: solo cargos autorizados (SOPORTE / ADMIN) pueden acceder o extraer auditorías."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.rol in (User.Rol.SOPORTE, User.Rol.ADMIN)
            and not request.user.debe_cambiar_clave
        )


class IsTitularOrAuthorizedDelegate(BasePermission):
    """
    Control ABAC Anti-BOLA / Anti-IDOR (Req. 106).
    Bloquea cualquier intento de operar sobre otra cédula sin DelegacionFamiliar activa,
    incluso si el atacante envía fecha_nacimiento.
    """

    message = "Acceso bloqueado (Anti-BOLA): no posee delegación familiar activa sobre la cédula solicitada."

    def _extract_target_cedula(self, request):
        for field in ("beneficiario_cedula", "afiliado_cedula", "afiliado_id", "cedula"):
            if field in request.query_params and request.query_params.get(field):
                return str(request.query_params.get(field)).strip()
            if hasattr(request, "data") and isinstance(request.data, dict):
                if field in request.data and request.data.get(field):
                    return str(request.data.get(field)).strip()
        return None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        target_cedula = self._extract_target_cedula(request)
        if target_cedula and target_cedula != request.user.cedula:
            if not es_cedula_ecuatoriana_valida(target_cedula):
                # Permite que el serializador/vista devuelva 400 Bad Request por cédula inválida
                return True
            return tiene_acceso_beneficiario(request.user, target_cedula)
        return True

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Turno):
            return tiene_acceso_beneficiario(request.user, obj.afiliado_id)
        return False

