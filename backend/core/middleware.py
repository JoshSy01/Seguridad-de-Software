import copy
import json
import re
import time

from django.core.cache import cache
from django.http import JsonResponse

from .models import AuditLog

REDACTED_VALUE = "[REDACTED]"

SENSITIVE_KEYS = {
    "password",
    "old_password",
    "current_password",
    "new_password",
    "confirm_password",
    "token",
    "access",
    "refresh",
    "access_token",
    "refresh_token",
    "otp",
    "debug_otp",
    "codigo_otp",
    "authorization",
    "http_authorization",
}

SENSITIVE_SUBSTRINGS = ("password", "token", "otp", "secret", "authorization")
JWT_REGEX = re.compile(r"^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

# Patrones de detección perimetral contra vectores de Inyección SQL (WAF Ligero)
SQLI_PATTERNS = re.compile(
    r"(\bunion\s+(all\s+)?select\b|"
    r"'\s*(or|and)\b|"
    r"\b(or|and)\s+\d+\s*=\s*\d+|"
    r";\s*(select|drop|delete|update|insert|alter|truncate|create|exec|execute)\b|"
    r"--\s*$|--\s+|/\*.*\*/|"
    r"\b(pg_sleep|sleep|benchmark|waitfor\s+delay|information_schema|pg_catalog)\b)",
    re.IGNORECASE,
)

PASSWORD_FIELDS_SKIP_WAF = {
    "password",
    "old_password",
    "current_password",
    "new_password",
    "confirm_password",
}


def contiene_patron_sqli(data, parent_key: str = "") -> bool:
    """Inspecciona recursivamente parámetros y cargas JSON buscando firmas de SQL Injection."""
    if parent_key.lower() in PASSWORD_FIELDS_SKIP_WAF:
        return False
    if isinstance(data, dict):
        return any(contiene_patron_sqli(v, str(k)) for k, v in data.items())
    if isinstance(data, list):
        return any(contiene_patron_sqli(item, parent_key) for item in data)
    if isinstance(data, str):
        return bool(SQLI_PATTERNS.search(data))
    return False


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")


def sanitize_payload(data):
    """
    Sanitizador recursivo (Log Scrubber - Req. 111).
    Reemplaza credenciales, OTPs, cabeceras Authorization y tokens JWT por "[REDACTED]".
    """
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            key_lower = str(key).lower()
            if key_lower in SENSITIVE_KEYS or any(sub in key_lower for sub in SENSITIVE_SUBSTRINGS):
                cleaned[key] = REDACTED_VALUE
            else:
                cleaned[key] = sanitize_payload(value)
        return cleaned
    if isinstance(data, list):
        return [sanitize_payload(item) for item in data]
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.lower().startswith("bearer ") or JWT_REGEX.match(stripped):
            return REDACTED_VALUE
        return data
    return data


class SQLInjectionGuardMiddleware:
    """
    Defensa perimetral contra Inyección SQL (complementaria al uso 100% parametrizado del ORM).
    Bloquea cargas maliciosas en query strings y JSON antes de alcanzar la capa de negocio.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/"):
            for key, values in request.GET.lists():
                if any(contiene_patron_sqli(val, key) for val in values):
                    return JsonResponse(
                        {
                            "detail": "Solicitud bloqueada: se detectaron caracteres o patrones de inyección SQL no permitidos."
                        },
                        status=400,
                    )

            if request.body and "application/json" in request.META.get("CONTENT_TYPE", ""):
                try:
                    parsed = json.loads(request.body.decode("utf-8"))
                    if contiene_patron_sqli(parsed):
                        return JsonResponse(
                            {
                                "detail": "Solicitud bloqueada: se detectaron patrones de inyección SQL en el cuerpo de la petición."
                            },
                            status=400,
                        )
                except Exception:
                    pass

        return self.get_response(request)


class RateLimitMiddleware:
    """
    Control de tasa por IP y por Usuario/Actor sobre `/api/*` (Req. 101).
    """

    WINDOW_SECONDS = 60
    MAX_REQUESTS_PER_IP = 200
    MAX_REQUESTS_PER_USER = 120

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/") and request.path != "/api/health/":
            ip = get_client_ip(request)
            bucket = int(time.time() // self.WINDOW_SECONDS)
            ip_key = f"ratelimit:ip:{ip}:{bucket}"
            try:
                current_ip = int(cache.get(ip_key, 0)) + 1
                cache.set(ip_key, current_ip, timeout=self.WINDOW_SECONDS + 5)
                if current_ip > self.MAX_REQUESTS_PER_IP:
                    return JsonResponse(
                        {"detail": "Límite de peticiones por IP excedido (Rate Limiting Req. 101)."},
                        status=429,
                    )

                auth_hdr = request.META.get("HTTP_AUTHORIZATION", "")
                if auth_hdr.startswith("Bearer "):
                    token_fp = auth_hdr[-24:]
                    usr_key = f"ratelimit:usr:{token_fp}:{bucket}"
                    current_usr = int(cache.get(usr_key, 0)) + 1
                    cache.set(usr_key, current_usr, timeout=self.WINDOW_SECONDS + 5)
                    if current_usr > self.MAX_REQUESTS_PER_USER:
                        return JsonResponse(
                            {"detail": "Límite de peticiones por sesión de usuario excedido (Req. 101)."},
                            status=429,
                        )
            except Exception:
                pass

        response = self.get_response(request)

        if request.path.startswith("/api/"):
            response["X-Robots-Tag"] = "noai, noimageai, noindex, nofollow"
            response["X-LOPDP-Policy"] = "Custodia-Exclusiva-IESS; Retencion-Max-5Y; Prohibido-IA-Externa"
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"

        return response


class AuditLogMiddleware:
    """
    Middleware de auditoría inmutable obligatoria (Req. 111).
    Intercepta todas las rutas `/api/*`, clona y sanitiza recursivamente el payload
    y cabeceras sensibles antes de insertar en `core_auditlog`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/") or request.path == "/api/health/":
            return self.get_response(request)

        cloned_body = {}
        raw_cedula_hint = None

        if request.body:
            try:
                parsed = json.loads(request.body.decode("utf-8"))
                if isinstance(parsed, dict):
                    cloned_body = copy.deepcopy(parsed)
                    raw_cedula_hint = parsed.get("cedula")
                else:
                    cloned_body = {"_items": copy.deepcopy(parsed)}
            except Exception:
                cloned_body = {"_non_json_body": True}

        if request.GET:
            cloned_body["_query"] = dict(request.GET.items())

        headers_snapshot = {}
        if "HTTP_AUTHORIZATION" in request.META:
            headers_snapshot["Authorization"] = request.META.get("HTTP_AUTHORIZATION", "")

        response = self.get_response(request)

        response_tokens = {}
        content_type = response.get("Content-Type", "")
        if "application/json" in content_type and hasattr(response, "content") and response.content:
            try:
                resp_json = json.loads(response.content.decode("utf-8"))
                if isinstance(resp_json, dict):
                    for k in ("access", "refresh", "token", "debug_otp", "otp"):
                        if k in resp_json:
                            response_tokens[k] = resp_json[k]
            except Exception:
                pass

        if headers_snapshot:
            cloned_body["_headers"] = headers_snapshot
        if response_tokens:
            cloned_body["_response"] = response_tokens

        user_session = getattr(request, "user_session", None)
        if user_session is not None:
            cloned_body["_session_id"] = str(user_session.id)

        sanitized = sanitize_payload(cloned_body)

        usuario_cedula = None
        rol = None
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            usuario_cedula = user.cedula
            rol = user.rol
        elif raw_cedula_hint:
            usuario_cedula = str(raw_cedula_hint)[:20]

        try:
            AuditLog.objects.create(
                usuario_cedula=usuario_cedula,
                rol=rol,
                ip=get_client_ip(request),
                metodo=request.method,
                ruta=request.path[:255],
                payload_sanitizado=sanitized,
                status_code=response.status_code,
            )
        except Exception:
            pass

        return response
