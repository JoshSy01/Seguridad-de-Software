import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "iess-prod-sec-key-9f8e7d6c5b4a3210-lopdp-2026-hmac-sha256",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "corsheaders",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.AuditLogMiddleware",
    "core.middleware.RateLimitMiddleware",
    "core.middleware.SQLInjectionGuardMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "iess_turnos_db"),
        "USER": os.environ.get("POSTGRES_USER", "iess_sec_admin"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "Iess_S3cur3_DB_2026!"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 30,
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache_table",
    }
}

AUTH_USER_MODEL = "core.User"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.permissions.SessionValidatedJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=8),
    "ROTATE_REFRESH_TOKENS": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "USER_ID_FIELD": "cedula",
    "USER_ID_CLAIM": "user_id",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_EXPOSE_HEADERS = ["Content-Disposition", "X-Audit-SHA256"]

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

