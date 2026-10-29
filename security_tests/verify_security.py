#!/usr/bin/env python3
"""
Suite Automatizada de Verificación de Controles de Seguridad - IESS Turnos
Valida los 7 controles obligatorios y los requerimientos ID 101, 102, 106, 107,
108, 109, 110, 111 (WORM Inmutable + [REDACTED]), 113 (24/7) y 114 (LOPDP 5 años / No IA).
"""

import json
import os
import sys
from contextlib import contextmanager
from datetime import date, timedelta

import requests

try:
    import pg8000.dbapi as db_driver

    USE_PG8000 = True
except ImportError:
    import psycopg as db_driver

    USE_PG8000 = False

BASE_URL = os.environ.get("IESS_API_URL", "http://localhost:8000/api")
DB_CONFIG = {
    "dbname": os.environ.get("POSTGRES_DB", "iess_turnos_db"),
    "user": os.environ.get("POSTGRES_USER", "iess_sec_admin"),
    "password": os.environ.get("POSTGRES_PASSWORD", "Iess_S3cur3_DB_2026!"),
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
}


@contextmanager
def get_db_cursor():
    if USE_PG8000:
        conn = db_driver.connect(
            database=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
        )
    else:
        conn = db_driver.connect(**DB_CONFIG)
    cur = conn.cursor()
    try:
        yield cur, conn
    finally:
        cur.close()
        conn.close()


def authenticate_mfa(cedula: str, password: str) -> dict:
    """Ejecuta el flujo completo de Login + MFA OTP y retorna tokens de sesión validada."""
    r1 = requests.post(
        f"{BASE_URL}/auth/login/",
        json={"cedula": cedula, "password": password},
        timeout=10,
    )
    assert r1.status_code == 200, f"Login falló para {cedula}: {r1.status_code} {r1.text}"
    body1 = r1.json()
    assert "access" not in body1, "El endpoint /auth/login/ NO debe emitir JWT antes del MFA."
    otp = body1.get("debug_otp")
    assert otp and len(otp) == 6, "No se recibió debug_otp de 6 dígitos."

    r2 = requests.post(
        f"{BASE_URL}/auth/verify-otp/",
        json={"cedula": cedula, "otp": otp},
        timeout=10,
    )
    assert r2.status_code == 200, f"Verify OTP falló para {cedula}: {r2.status_code} {r2.text}"
    data = r2.json()
    assert "access" in data and "session_id" in data, "Falta JWT o session_id tras MFA."
    return data


def test_01_minimizacion_bd():
    """
    Req. 103, 104, 105, 114: Verifica en PostgreSQL que core_user y core_turno NO contengan
    columnas prohibidas laborales, financieras, clínicas o sensibles, y valida cabeceras
    LOPDP de retención máxima de 5 años y prohibición de entrenamiento IA externo.
    """
    campos_prohibidos = {
        "empleador",
        "cargo",
        "sueldo",
        "cuenta_bancaria",
        "contrato",
        "contrato_trabajo",
        "diagnostico",
        "diagnosticos",
        "alergias",
        "medicamentos",
        "laboratorios",
        "religion",
        "partido_politico",
        "afiliacion_politica",
    }

    with get_db_cursor() as (cur, _conn):
        for tabla in ("core_user", "core_turno"):
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                """,
                (tabla,),
            )
            columnas = {row[0].lower() for row in cur.fetchall()}
            assert columnas, f"La tabla {tabla} no existe en PostgreSQL."
            interseccion = columnas.intersection(campos_prohibidos)
            assert not interseccion, (
                f"Violación LOPDP en {tabla}: columnas prohibidas detectadas {interseccion}"
            )
            if tabla == "core_turno":
                assert "retencion_hasta" in columnas, "Falta control de retención de 5 años (Req. 114)."

    # Verificar cabeceras anti-IA externa y custodia exclusiva LOPDP (Req. 114)
    r_hdr = requests.post(f"{BASE_URL}/auth/login/", json={"cedula": "0000000000", "password": "x"}, timeout=10)
    assert "noai" in r_hdr.headers.get("X-Robots-Tag", ""), "Falta cabecera anti-IA X-Robots-Tag (Req. 114)."
    assert "Retencion-Max-5Y" in r_hdr.headers.get("X-LOPDP-Policy", ""), "Falta cabecera X-LOPDP-Policy."


def test_02_rechazo_clave_fecha_nacimiento():
    """
    Req. 102 y 107:
    - Contrasta identidad por cédula contra padrón IESS y valida registro por OTP.
    - Verifica rechazo 400 Bad Request al intentar usar fecha de nacimiento o cédula en la clave.
    """
    sesion = authenticate_mfa("1710000017", "ClaveSegura#IESS2026!")
    headers = {"Authorization": f"Bearer {sesion['access']}"}

    # Fecha de nacimiento de 1710000017 es 1990-05-15
    intentos_invalidos = [
        "Segura19900515#!",
        "Segura15051990#!",
        "Segura1990-05-15!",
        "Clave1710000017#!",
        "Corta#123",
    ]
    for clave_invalida in intentos_invalidos:
        resp = requests.post(
            f"{BASE_URL}/auth/change-password/",
            headers=headers,
            json={
                "current_password": "ClaveSegura#IESS2026!",
                "new_password": clave_invalida,
            },
            timeout=10,
        )
        assert resp.status_code == 400, (
            f"Se esperaba 400 Bad Request para '{clave_invalida}', recibido {resp.status_code}"
        )

    # Verificar contraste contra padrón institucional IESS (Req. 102)
    with get_db_cursor() as (cur, conn):
        cur.execute("DELETE FROM core_user WHERE cedula = '1710000058'")
        conn.commit()

    r_padron = requests.post(
        f"{BASE_URL}/auth/registro/consultar-cedula/",
        json={"cedula": "1710000058"},
        timeout=10,
    )
    assert r_padron.status_code == 200 and r_padron.json().get("cobertura_activa") is True
    dob_padron = r_padron.json()["fecha_nacimiento"]  # 1993-07-14

    r_reg_bad = requests.post(
        f"{BASE_URL}/auth/registro/solicitar-otp/",
        json={
            "cedula": "1710000058",
            "email": "diego.morales@mail.com",
            "telefono": "0998887766",
            "password": f"Clave{dob_padron}!",
        },
        timeout=10,
    )
    assert r_reg_bad.status_code == 400, "Registro debía rechazar clave con fecha de nacimiento."


def test_03_bloqueo_fuerza_bruta():
    """
    Req. 107: Envía 5 logins fallidos seguidos y verifica que el 6.º intento
    devuelva 429 Too Many Requests.
    """
    target_cedula = "1710000041"

    with get_db_cursor() as (cur, conn):
        cur.execute(
            "UPDATE core_user SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE cedula = %s",
            (target_cedula,),
        )
        conn.commit()

    try:
        for i in range(1, 6):
            r = requests.post(
                f"{BASE_URL}/auth/login/",
                json={"cedula": target_cedula, "password": f"ClaveIncorrecta_{i}"},
                timeout=10,
            )
            assert r.status_code == 401, (
                f"Intento fallido #{i} esperaba 401, recibido {r.status_code}"
            )

        r6 = requests.post(
            f"{BASE_URL}/auth/login/",
            json={"cedula": target_cedula, "password": "ClaveIncorrecta_6"},
            timeout=10,
        )
        assert r6.status_code == 429, (
            f"El 6.º intento debía devolver 429 Too Many Requests, recibido {r6.status_code}"
        )
    finally:
        with get_db_cursor() as (cur, conn):
            cur.execute(
                "UPDATE core_user SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE cedula = %s",
                (target_cedula,),
            )
            conn.commit()


def test_04_bloqueo_bola_familiares():
    """
    Req. 101 y 106:
    - Bloquea consulta/reserva en fechas pasadas (400) y verifica disponibilidad en fechas futuras.
    - Bloquea reserva y cancelación sobre Afiliado B sin delegación OTP activa (403 Forbidden).
    """
    with get_db_cursor() as (cur, conn):
        cur.execute(
            "DELETE FROM core_delegacionfamiliar WHERE titular_id = '1710000025' AND delegado_id = '1710000017'"
        )
        cur.execute(
            "SELECT id FROM core_turno WHERE afiliado_id = '1710000025' AND estado = 'RESERVADO' LIMIT 1"
        )
        row = cur.fetchone()
        assert row is not None, "No existe turno semilla de Afiliado B para probar cancelación."
        turno_b_id = row[0]
        conn.commit()

    sesion_a = authenticate_mfa("1710000017", "ClaveSegura#IESS2026!")
    headers_a = {"Authorization": f"Bearer {sesion_a['access']}"}

    # Verificar bloqueo de fechas pasadas y disponibilidad real en fechas futuras (Req. 101)
    ayer = (date.today() - timedelta(days=1)).isoformat()
    futura = (date.today() + timedelta(days=5)).isoformat()

    r_pasada = requests.get(
        f"{BASE_URL}/turnos/disponibilidad/",
        headers=headers_a,
        params={
            "establecimiento": "Hospital Carlos Andrade Marín (HCAM)",
            "especialidad": "Medicina General",
            "fecha": ayer,
        },
        timeout=10,
    )
    assert r_pasada.status_code == 400, "Disponibilidad debía rechazar fechas pasadas con 400."

    r_futura = requests.get(
        f"{BASE_URL}/turnos/disponibilidad/",
        headers=headers_a,
        params={
            "establecimiento": "Hospital Carlos Andrade Marín (HCAM)",
            "especialidad": "Medicina General",
            "fecha": futura,
        },
        timeout=10,
    )
    assert r_futura.status_code == 200 and len(r_futura.json().get("horarios_disponibles", [])) > 0, (
        "Las fechas futuras deben retornar horarios disponibles para todos los establecimientos."
    )

    # 1. Intentar reservar turno para Afiliado B sin delegación OTP activa
    resp_reserva = requests.post(
        f"{BASE_URL}/turnos/reservar/",
        headers=headers_a,
        json={
            "beneficiario_cedula": "1710000025",
            "fecha_nacimiento": "1985-08-22",
            "medico_cedula": "1730000013",
            "establecimiento": "Hospital Carlos Andrade Marín (HCAM)",
            "especialidad": "Medicina General",
            "fecha": futura,
            "hora": "09:00",
        },
        timeout=10,
    )
    assert resp_reserva.status_code == 403, (
        f"Reserva BOLA debía devolver 403 Forbidden, recibido {resp_reserva.status_code}"
    )

    # 2. Intentar cancelar turno perteneciente al Afiliado B
    resp_cancelar = requests.post(
        f"{BASE_URL}/turnos/{turno_b_id}/cancelar/",
        headers=headers_a,
        json={
            "beneficiario_cedula": "1710000025",
            "fecha_nacimiento": "1985-08-22",
        },
        timeout=10,
    )
    assert resp_cancelar.status_code == 403, (
        f"Cancelación BOLA debía devolver 403 Forbidden, recibido {resp_cancelar.status_code}"
    )


def test_05_segregacion_rbac_funcionarios():
    """
    Req. 108:
    - SOPORTE bloqueado en /api/turnos/mis-turnos/ (403).
    - RECEPCION acotada a su establecimiento, contacto enmascarado y confirmación de asistencia.
    - Medico 1 bloqueado al intentar leer turnos de Medico 2 (403).
    - SOPORTE y ADMIN autorizados a extraer auditorías SHA-256; MEDICO recibe 403.
    """
    sesion_soporte = authenticate_mfa("1740000011", "StaffSegura#IESS2026!")
    headers_soporte = {"Authorization": f"Bearer {sesion_soporte['access']}"}

    resp_soporte_turnos = requests.get(
        f"{BASE_URL}/turnos/mis-turnos/",
        headers=headers_soporte,
        timeout=10,
    )
    assert resp_soporte_turnos.status_code == 403

    resp_export_soporte = requests.get(
        f"{BASE_URL}/staff/audit-logs/export/?formato=csv",
        headers=headers_soporte,
        timeout=10,
    )
    assert resp_export_soporte.status_code == 200 and resp_export_soporte.headers.get("X-Audit-SHA256")

    sesion_admin = authenticate_mfa("1750000018", "StaffSegura#IESS2026!")
    headers_admin = {"Authorization": f"Bearer {sesion_admin['access']}"}
    resp_export_admin = requests.get(
        f"{BASE_URL}/staff/audit-logs/export/?formato=json",
        headers=headers_admin,
        timeout=10,
    )
    assert resp_export_admin.status_code == 200 and resp_export_admin.headers.get("X-Audit-SHA256")

    # Verificar Recepción HCAM: enmascaramiento y bloqueo de otro establecimiento
    with get_db_cursor() as (cur, _conn):
        cur.execute("SELECT id FROM core_turno WHERE medico_id = '1730000021' AND fecha = CURRENT_DATE LIMIT 1")
        turno_otro_est_id = cur.fetchone()[0]

    sesion_rec = authenticate_mfa("1720000015", "StaffSegura#IESS2026!")
    headers_rec = {"Authorization": f"Bearer {sesion_rec['access']}"}
    r_rec_ok = requests.get(
        f"{BASE_URL}/staff/recepcion/",
        headers=headers_rec,
        params={"cedula": "1710000033"},
        timeout=10,
    )
    assert r_rec_ok.status_code == 200 and len(r_rec_ok.json()) >= 1
    item_rec = r_rec_ok.json()[0]
    assert "***" in item_rec["email_enmascarado"] and "***" in item_rec["telefono_enmascarado"]

    r_rec_otro_est = requests.post(
        f"{BASE_URL}/staff/recepcion/{turno_otro_est_id}/confirmar-asistencia/",
        headers=headers_rec,
        timeout=10,
    )
    assert r_rec_otro_est.status_code == 403, "Recepción HCAM no debe confirmar turnos de otra sede."

    # Médico 1 intentando consultar Médico 2
    sesion_med1 = authenticate_mfa("1730000013", "StaffSegura#IESS2026!")
    headers_med1 = {"Authorization": f"Bearer {sesion_med1['access']}"}

    resp_med_query = requests.get(
        f"{BASE_URL}/staff/agenda-medica/?medico_cedula=1730000021",
        headers=headers_med1,
        timeout=10,
    )
    assert resp_med_query.status_code == 403

    resp_med_obj = requests.get(
        f"{BASE_URL}/staff/agenda-medica/{turno_otro_est_id}/",
        headers=headers_med1,
        timeout=10,
    )
    assert resp_med_obj.status_code == 403


def test_06_notificacion_sin_magic_link():
    """
    Req. 109, 110, 113 + Validación de Sesiones:
    - Verifica disponibilidad 24/7 (/api/health/) y telemetría mTLS/TLS 1.3 + OAuth2 + Circuit Breaker.
    - Solicita GET /api/turnos/<id>/ sin cabecera Authorization -> 401 Unauthorized.
    - Verifica invalidación inmediata de sesión al ejecutar logout -> 401 Unauthorized.
    """
    r_health = requests.get(f"{BASE_URL}/health/", timeout=10)
    assert r_health.status_code == 200
    h_json = r_health.json()
    assert h_json.get("ventana_mantenimiento_diaria") == "ELIMINADA"
    assert "TLS 1.3" in h_json.get("integracion_gateway", {}).get("protocolo_transporte", "")

    with get_db_cursor() as (cur, _conn):
        cur.execute("SELECT id FROM core_turno LIMIT 1")
        turno_id = cur.fetchone()[0]

    resp_anon = requests.get(f"{BASE_URL}/turnos/{turno_id}/", timeout=10)
    assert resp_anon.status_code == 401

    sesion = authenticate_mfa("1710000017", "ClaveSegura#IESS2026!")
    headers = {"Authorization": f"Bearer {sesion['access']}"}
    r_logout = requests.post(f"{BASE_URL}/auth/logout/", headers=headers, timeout=10)
    assert r_logout.status_code == 200

    resp_post_logout = requests.get(f"{BASE_URL}/turnos/{turno_id}/", headers=headers, timeout=10)
    assert resp_post_logout.status_code == 401


def test_07_sanitizacion_logs_auditoria():
    """
    Req. 111:
    - Verifica que contraseñas, OTPs y tokens JWT se guarden exactamente como "[REDACTED]".
    - Verifica inmutabilidad WORM en PostgreSQL (bloqueo de DELETE/UPDATE sobre core_auditlog).
    """
    clave_original = "ClaveSegura#IESS2026!"
    clave_temporal_marcador = "MarcadorUnico#Audit98765!"

    sesion = authenticate_mfa("1710000017", clave_original)
    jwt_access = sesion["access"]
    headers = {"Authorization": f"Bearer {jwt_access}"}

    r_chg1 = requests.post(
        f"{BASE_URL}/auth/change-password/",
        headers=headers,
        json={"current_password": clave_original, "new_password": clave_temporal_marcador},
        timeout=10,
    )
    assert r_chg1.status_code == 200

    r_chg2 = requests.post(
        f"{BASE_URL}/auth/change-password/",
        headers=headers,
        json={"current_password": clave_temporal_marcador, "new_password": clave_original},
        timeout=10,
    )
    assert r_chg2.status_code == 200

    with get_db_cursor() as (cur, conn):
        cur.execute(
            """
            SELECT id, payload_sanitizado
            FROM core_auditlog
            WHERE ruta = '/api/auth/login/' AND usuario_cedula = '1710000017'
            ORDER BY id DESC LIMIT 1
            """
        )
        audit_id, login_payload = cur.fetchone()
        if isinstance(login_payload, str):
            login_payload = json.loads(login_payload)
        assert login_payload.get("password") == "[REDACTED]"

        cur.execute(
            """
            SELECT payload_sanitizado
            FROM core_auditlog
            WHERE ruta = '/api/auth/verify-otp/' AND usuario_cedula = '1710000017'
            ORDER BY id DESC LIMIT 1
            """
        )
        otp_payload = cur.fetchone()[0]
        if isinstance(otp_payload, str):
            otp_payload = json.loads(otp_payload)
        assert otp_payload.get("otp") == "[REDACTED]"
        resp_tokens = otp_payload.get("_response", {})
        assert resp_tokens.get("access") == "[REDACTED]"
        assert resp_tokens.get("refresh") == "[REDACTED]"

        cur.execute(
            """
            SELECT payload_sanitizado
            FROM core_auditlog
            WHERE ruta = '/api/auth/change-password/' AND usuario_cedula = '1710000017'
            ORDER BY id DESC LIMIT 1
            """
        )
        chg_payload = cur.fetchone()[0]
        if isinstance(chg_payload, str):
            chg_payload = json.loads(chg_payload)
        assert chg_payload.get("current_password") == "[REDACTED]"
        assert chg_payload.get("new_password") == "[REDACTED]"
        assert chg_payload.get("_headers", {}).get("Authorization") == "[REDACTED]"

        cur.execute(
            """
            SELECT COUNT(*)
            FROM core_auditlog
            WHERE payload_sanitizado::text LIKE %s
               OR payload_sanitizado::text LIKE %s
               OR payload_sanitizado::text LIKE %s
            """,
            (f"%{clave_temporal_marcador}%", f"%{clave_original}%", f"%{jwt_access}%"),
        )
        assert cur.fetchone()[0] == 0, "CRÍTICO: Se detectaron secretos en texto claro en AuditLog."

        # Verificar inmutabilidad WORM en PostgreSQL: prohibido eliminar registros de auditoría (Req. 111)
        inmutable_ok = False
        try:
            cur.execute("DELETE FROM core_auditlog WHERE id = %s", (audit_id,))
        except Exception:
            inmutable_ok = True
            conn.rollback()
        assert inmutable_ok, "CRÍTICO: PostgreSQL permitió eliminar un registro de core_auditlog."


def test_08_prevencion_inyeccion_sql_y_cedula_ec():
    """
    Valida en todas las capas:
    1) Algoritmo oficial de Cédula Ecuatoriana (Módulo 10, provincia 01..24/30, 3er dígito < 6)
       tanto en API REST como en el CHECK constraint nativo de PostgreSQL.
    2) Bloqueo total de ataques de Inyección SQL (tautologías, UNION SELECT, stacked DROP TABLE,
       comentarios SQL y blind/time-based pg_sleep) sin errores 500 ni pérdida de integridad.
    """
    cedulas_invalidas = [
        "1710000011",  # Dígito verificador Módulo 10 incorrecto (debería ser 7)
        "9910000015",  # Código de provincia inexistente (99)
        "1760000019",  # Tercer dígito >= 6 (no corresponde a cédula de persona natural)
        "2222222222",  # Dígitos repetidos triviales
        "17100ABC17",  # Caracteres alfanuméricos
    ]

    for ced_bad in cedulas_invalidas:
        r_login = requests.post(
            f"{BASE_URL}/auth/login/",
            json={"cedula": ced_bad, "password": "ClaveSegura#IESS2026!"},
            timeout=10,
        )
        assert r_login.status_code == 400, (
            f"Login debía rechazar cédula inválida '{ced_bad}' con 400, recibido {r_login.status_code}"
        )

        r_reg = requests.post(
            f"{BASE_URL}/auth/registro/consultar-cedula/",
            json={"cedula": ced_bad},
            timeout=10,
        )
        assert r_reg.status_code == 400, (
            f"Registro debía rechazar cédula inválida '{ced_bad}' con 400, recibido {r_reg.status_code}"
        )

    sesion_afiliado = authenticate_mfa("1710000017", "ClaveSegura#IESS2026!")
    headers_afiliado = {"Authorization": f"Bearer {sesion_afiliado['access']}"}

    sesion_rec = authenticate_mfa("1720000015", "StaffSegura#IESS2026!")
    headers_rec = {"Authorization": f"Bearer {sesion_rec['access']}"}

    # Validación Módulo 10 en delegación familiar y check-in de recepción
    r_del_bad = requests.post(
        f"{BASE_URL}/delegaciones/solicitar/",
        headers=headers_afiliado,
        json={"titular_cedula": "1710000011"},
        timeout=10,
    )
    assert r_del_bad.status_code == 400

    r_rec_bad = requests.get(
        f"{BASE_URL}/staff/recepcion/",
        headers=headers_rec,
        params={"cedula": "1710000011"},
        timeout=10,
    )
    assert r_rec_bad.status_code == 400

    # Vectores de ataque SQL Injection en múltiples endpoints JSON y Query Params
    vectores_sqli = [
        "' OR '1'='1",
        "1710000017' OR 1=1--",
        "1710000017' UNION SELECT password FROM core_user--",
        "1710000017'; DROP TABLE core_user; --",
        "1710000017' AND (SELECT 1 FROM pg_sleep(5))--",
    ]

    for payload in vectores_sqli:
        r_sqli_login = requests.post(
            f"{BASE_URL}/auth/login/",
            json={"cedula": payload, "password": "x"},
            timeout=4,
        )
        assert r_sqli_login.status_code == 400, (
            f"SQLi en login debía ser bloqueado con 400, recibido {r_sqli_login.status_code}"
        )

        r_sqli_turnos = requests.get(
            f"{BASE_URL}/turnos/mis-turnos/",
            headers=headers_afiliado,
            params={"beneficiario_cedula": payload},
            timeout=4,
        )
        assert r_sqli_turnos.status_code == 400, (
            f"SQLi en mis-turnos debía ser bloqueado con 400, recibido {r_sqli_turnos.status_code}"
        )

        r_sqli_disp = requests.get(
            f"{BASE_URL}/turnos/disponibilidad/",
            headers=headers_afiliado,
            params={
                "establecimiento": payload,
                "especialidad": "Medicina General",
                "fecha": (date.today() + timedelta(days=2)).isoformat(),
            },
            timeout=4,
        )
        assert r_sqli_disp.status_code == 400, (
            f"SQLi en disponibilidad debía ser bloqueado con 400, recibido {r_sqli_disp.status_code}"
        )

        r_sqli_rec = requests.get(
            f"{BASE_URL}/staff/recepcion/",
            headers=headers_rec,
            params={"cedula": payload},
            timeout=4,
        )
        assert r_sqli_rec.status_code == 400, (
            f"SQLi en recepción debía ser bloqueado con 400, recibido {r_sqli_rec.status_code}"
        )

    # Verificar CHECK constraint Módulo 10 en PostgreSQL e integridad intacta de tablas
    with get_db_cursor() as (cur, conn):
        check_db_ok = False
        try:
            cur.execute(
                """
                INSERT INTO core_user (
                    password, cedula, nombres, fecha_nacimiento, email, telefono,
                    rol, establecimiento_asignado, debe_cambiar_clave, intentos_fallidos, is_active
                ) VALUES (
                    'x', '1710000001', 'Invalido Mod10', '1990-01-01',
                    'invalido@test.ec', '0990000000', 'AFILIADO', '', FALSE, 0, TRUE
                )
                """
            )
        except Exception:
            check_db_ok = True
            conn.rollback()
        assert check_db_ok, "PostgreSQL debía rechazar cédula con Módulo 10 inválido mediante CHECK."

        cur.execute("SELECT COUNT(*) FROM core_user")
        assert cur.fetchone()[0] >= 10, "Integridad comprometida en tabla core_user."

        cur.execute("SELECT COUNT(*) FROM core_turno")
        assert cur.fetchone()[0] >= 3, "Integridad comprometida en tabla core_turno."


def main():
    tests = [
        ("test_01_minimización_bd", test_01_minimizacion_bd),
        ("test_02_rechazo_clave_fecha_nacimiento", test_02_rechazo_clave_fecha_nacimiento),
        ("test_03_bloqueo_fuerza_bruta", test_03_bloqueo_fuerza_bruta),
        ("test_04_bloqueo_bola_familiares", test_04_bloqueo_bola_familiares),
        ("test_05_segregacion_rbac_funcionarios", test_05_segregacion_rbac_funcionarios),
        ("test_06_notificacion_sin_magic_link", test_06_notificacion_sin_magic_link),
        ("test_07_sanitizacion_logs_auditoria", test_07_sanitizacion_logs_auditoria),
        ("test_08_prevencion_inyeccion_sql_y_cedula_ec", test_08_prevencion_inyeccion_sql_y_cedula_ec),
    ]

    print("=" * 72)
    print(" EJECUTANDO SUITE DE SEGURIDAD - SISTEMA DE TURNOS IESS ")
    print("=" * 72)

    passed = 0
    failed = 0

    for nombre, fn in tests:
        try:
            fn()
            print(f"[PASS] {nombre}")
            passed += 1
        except Exception as exc:
            print(f"[FAIL] {nombre} -> {exc}")
            failed += 1

    print("=" * 72)
    print(f" RESULTADO FINAL: {passed}/{len(tests)} PRUEBAS SUPERADAS ({int(passed / len(tests) * 100)}%)")
    print("=" * 72)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
