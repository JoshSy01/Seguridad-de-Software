-- =============================================================================
-- SISTEMA SEGURO DE GESTIÓN DE TURNOS DEL IESS
-- Script Inicial de Base de Datos (PostgreSQL 16)
-- Cumplimiento estricto LOPDP: Minimización de Datos (Req. 102, 103, 104, 105, 114)
-- Validación nativa de Cédula Ecuatoriana (Módulo 10) e Inmutabilidad WORM.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Función nativa PostgreSQL para validar Cédula de Identidad Ecuatoriana (Módulo 10)
CREATE OR REPLACE FUNCTION es_cedula_ecuatoriana_valida(ced VARCHAR)
RETURNS BOOLEAN AS $$
DECLARE
    prov INT;
    tercer INT;
    suma INT := 0;
    coef INT[] := ARRAY[2, 1, 2, 1, 2, 1, 2, 1, 2];
    val INT;
    digito_verif INT;
    i INT;
BEGIN
    IF ced IS NULL OR ced !~ '^[0-9]{10}$' THEN
        RETURN FALSE;
    END IF;
    IF ced ~ '^([0-9])\1{9}$' THEN
        RETURN FALSE;
    END IF;

    prov := CAST(SUBSTRING(ced FROM 1 FOR 2) AS INT);
    IF NOT ((prov BETWEEN 1 AND 24) OR prov = 30) THEN
        RETURN FALSE;
    END IF;

    tercer := CAST(SUBSTRING(ced FROM 3 FOR 1) AS INT);
    IF tercer >= 6 THEN
        RETURN FALSE;
    END IF;

    FOR i IN 1..9 LOOP
        val := CAST(SUBSTRING(ced FROM i FOR 1) AS INT) * coef[i];
        IF val >= 10 THEN
            val := val - 9;
        END IF;
        suma := suma + val;
    END LOOP;

    digito_verif := (10 - (suma % 10)) % 10;
    RETURN digito_verif = CAST(SUBSTRING(ced FROM 10 FOR 1) AS INT);
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 1. Tabla Minimalista de Usuarios (Personalizada por Cédula Ecuatoriana Válida)
CREATE TABLE IF NOT EXISTS core_user (
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMPTZ NULL,
    cedula VARCHAR(10) PRIMARY KEY CHECK (es_cedula_ecuatoriana_valida(cedula)),
    nombres VARCHAR(150) NOT NULL,
    fecha_nacimiento DATE NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE,
    telefono VARCHAR(15) NOT NULL,
    rol VARCHAR(20) NOT NULL CHECK (rol IN ('AFILIADO', 'RECEPCION', 'MEDICO', 'ADMIN', 'SOPORTE')),
    establecimiento_asignado VARCHAR(120) NOT NULL DEFAULT '',
    debe_cambiar_clave BOOLEAN NOT NULL DEFAULT FALSE,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta TIMESTAMPTZ NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- 2. Catálogo Administrativo de Establecimientos (Req. 108 - Gestión Admin)
CREATE TABLE IF NOT EXISTS core_establecimiento (
    id BIGSERIAL PRIMARY KEY,
    nombre VARCHAR(120) NOT NULL UNIQUE,
    ciudad VARCHAR(80) NOT NULL DEFAULT 'Quito',
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 3. Tabla de Delegación Familiar (Anti-BOLA / Anti-IDOR - Req. 106)
CREATE TABLE IF NOT EXISTS core_delegacionfamiliar (
    id BIGSERIAL PRIMARY KEY,
    titular_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE CASCADE,
    delegado_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE CASCADE,
    tipo_vinculo VARCHAR(30) NOT NULL CHECK (tipo_vinculo IN ('HIJO_MENOR', 'ADULTO_AUTORIZADO')),
    activo BOOLEAN NOT NULL DEFAULT TRUE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_titular_delegado UNIQUE (titular_id, delegado_id)
);

-- 4. Tabla de Turnos Médicos (Sin diagnósticos - Req. 101, 104, Retención 5 años Req. 114)
CREATE TABLE IF NOT EXISTS core_turno (
    id BIGSERIAL PRIMARY KEY,
    afiliado_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE RESTRICT,
    reservado_por_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE RESTRICT,
    medico_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE RESTRICT,
    establecimiento VARCHAR(120) NOT NULL,
    especialidad VARCHAR(50) NOT NULL CHECK (especialidad IN ('Medicina General', 'Odontología', 'Psicología', 'Pediatría')),
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'RESERVADO' CHECK (estado IN ('RESERVADO', 'CANCELADO', 'ATENDIDO')),
    asistencia_confirmada BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retencion_hasta DATE NOT NULL DEFAULT (CURRENT_DATE + INTERVAL '5 years')::date,
    CONSTRAINT unique_medico_fecha_hora UNIQUE (medico_id, fecha, hora)
);

-- 5. Tabla Inmutable de Auditoría Sanitizada (Log Scrubber WORM - Req. 111)
CREATE TABLE IF NOT EXISTS core_auditlog (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usuario_cedula VARCHAR(20) NULL,
    rol VARCHAR(20) NULL,
    ip INET NULL,
    metodo VARCHAR(10) NOT NULL,
    ruta VARCHAR(255) NOT NULL,
    payload_sanitizado JSONB NOT NULL DEFAULT '{}'::jsonb,
    status_code INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auditlog_timestamp ON core_auditlog(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_auditlog_cedula ON core_auditlog(usuario_cedula);

-- Trigger de Inmutabilidad WORM en PostgreSQL: bloquea UPDATE y DELETE sobre core_auditlog (Req. 111)
CREATE OR REPLACE FUNCTION fn_proteger_inmutabilidad_auditlog()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Operación prohibida (Req. 111): Los registros de AuditLog son estrictamente inmutables.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_auditlog_inmutable ON core_auditlog;
CREATE TRIGGER trg_auditlog_inmutable
BEFORE UPDATE OR DELETE ON core_auditlog
FOR EACH ROW EXECUTE FUNCTION fn_proteger_inmutabilidad_auditlog();

-- 6. Tabla de Sesiones Validadas Stateful (Control de Sesiones Activas y Revocación)
CREATE TABLE IF NOT EXISTS core_usersession (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    usuario_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE CASCADE,
    jti_refresh VARCHAR(128) NOT NULL DEFAULT '',
    ip INET NULL,
    user_agent VARCHAR(255) NOT NULL DEFAULT '',
    mfa_verificado BOOLEAN NOT NULL DEFAULT FALSE,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultima_actividad TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expira_en TIMESTAMPTZ NOT NULL,
    motivo_cierre VARCHAR(64) NOT NULL DEFAULT ''
);

-- 7. Tabla de Horarios Médicos (Gestión Administrativa Anonimizada)
CREATE TABLE IF NOT EXISTS core_horariomedico (
    id BIGSERIAL PRIMARY KEY,
    medico_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE CASCADE,
    establecimiento VARCHAR(120) NOT NULL,
    especialidad VARCHAR(50) NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin TIME NOT NULL,
    intervalo_minutos INTEGER NOT NULL DEFAULT 30,
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

-- 8. Tabla de Notificaciones Seguras (SMS + Correo sin Magic Links ni Diagnósticos - Req. 109)
CREATE TABLE IF NOT EXISTS core_notificacion (
    id BIGSERIAL PRIMARY KEY,
    destinatario_id VARCHAR(10) NOT NULL REFERENCES core_user(cedula) ON DELETE CASCADE,
    turno_id BIGINT NOT NULL REFERENCES core_turno(id) ON DELETE CASCADE,
    tipo VARCHAR(20) NOT NULL,
    canal VARCHAR(30) NOT NULL DEFAULT 'SMS_Y_EMAIL',
    establecimiento VARCHAR(120) NOT NULL,
    especialidad VARCHAR(50) NOT NULL,
    fecha DATE NOT NULL,
    hora TIME NOT NULL,
    estado_turno VARCHAR(20) NOT NULL DEFAULT 'RESERVADO',
    enlace_relativo VARCHAR(120) NOT NULL,
    mensaje VARCHAR(255) NOT NULL,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
