import React, { useCallback, useEffect, useState } from "react";
import client, { exportAuditFile, validarCedulaEcuatoriana } from "../api/client";

export default function DashboardFuncionario({ user }) {
  const rol = user?.rol;

  // Estado RECEPCION
  const [cedulaBusqueda, setCedulaBusqueda] = useState("");
  const [citasRecepcion, setCitasRecepcion] = useState([]);
  const [busquedaRealizada, setBusquedaRealizada] = useState(false);

  // Estado MEDICO
  const [agendaMedica, setAgendaMedica] = useState([]);

  // Estado SOPORTE
  const [auditData, setAuditData] = useState({ metricas: null, logs: [] });

  // Estado ADMIN
  const [statsAdmin, setStatsAdmin] = useState({
    resumen_especialidades: [],
    sesiones_activas_sistema: 0,
    total_eventos_auditoria: 0,
    retencion_lopdp_anios: 5,
  });
  const [horariosData, setHorariosData] = useState({
    horarios: [],
    medicos: [],
    establecimientos: [],
    catalogo_establecimientos: [],
    especialidades: [],
  });
  const [nuevoHorario, setNuevoHorario] = useState({
    medico_cedula: "",
    establecimiento: "",
    especialidad: "",
    hora_inicio: "08:00",
    hora_fin: "12:00",
  });
  const [nuevoEstNombre, setNuevoEstNombre] = useState("");
  const [nuevoEstCiudad, setNuevoEstCiudad] = useState("Quito");

  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");

  const cargarDatosPorRol = useCallback(async () => {
    setError("");
    try {
      if (rol === "MEDICO") {
        const { data } = await client.get("/staff/agenda-medica/");
        setAgendaMedica(data);
      } else if (rol === "SOPORTE") {
        const { data } = await client.get("/staff/audit-logs/");
        setAuditData(data);
      } else if (rol === "ADMIN") {
        const [resStats, resHor] = await Promise.all([
          client.get("/staff/admin/estadisticas/"),
          client.get("/staff/admin/horarios/"),
        ]);
        setStatsAdmin(resStats.data);
        setHorariosData(resHor.data);
        setNuevoHorario((prev) => ({
          ...prev,
          medico_cedula: prev.medico_cedula || resHor.data.medicos?.[0]?.cedula || "",
          establecimiento:
            prev.establecimiento || resHor.data.establecimientos?.[0] || "",
          especialidad: prev.especialidad || resHor.data.especialidades?.[0] || "",
        }));
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Error al cargar información operativa.");
    }
  }, [rol]);

  useEffect(() => {
    cargarDatosPorRol();
  }, [cargarDatosPorRol]);

  const buscarCheckin = async (e) => {
    e?.preventDefault();
    setError("");
    setMensaje("");
    try {
      const { data } = await client.get("/staff/recepcion/", {
        params: { cedula: cedulaBusqueda },
      });
      setCitasRecepcion(data);
      setBusquedaRealizada(true);
    } catch (err) {
      setError(err.response?.data?.detail || "Error al buscar citas del día.");
    }
  };

  const confirmarAsistenciaRecepcion = async (id) => {
    setError("");
    setMensaje("");
    try {
      await client.post(`/staff/recepcion/${id}/confirmar-asistencia/`);
      setMensaje("Asistencia del paciente confirmada en recepción.");
      await buscarCheckin();
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo confirmar la asistencia.");
    }
  };

  const marcarAtendido = async (id) => {
    setError("");
    try {
      await client.post(`/staff/agenda-medica/${id}/atender/`);
      setMensaje("Cita marcada como ATENDIDA.");
      await cargarDatosPorRol();
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo actualizar el turno.");
    }
  };

  const crearHorario = async (e) => {
    e.preventDefault();
    setError("");
    setMensaje("");
    try {
      await client.post("/staff/admin/horarios/", nuevoHorario);
      setMensaje("Horario médico registrado correctamente.");
      await cargarDatosPorRol();
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo registrar el horario.");
    }
  };

  const crearEstablecimiento = async (e) => {
    e.preventDefault();
    if (!nuevoEstNombre.trim()) return;
    setError("");
    setMensaje("");
    try {
      await client.post("/staff/admin/catalogo/", {
        nombre: nuevoEstNombre.trim(),
        ciudad: nuevoEstCiudad.trim() || "Quito",
        activo: true,
      });
      setNuevoEstNombre("");
      setMensaje("Establecimiento agregado al catálogo oficial.");
      await cargarDatosPorRol();
    } catch (err) {
      setError(
        err.response?.data?.nombre?.[0] ||
          err.response?.data?.detail ||
          "No se pudo agregar el establecimiento."
      );
    }
  };

  const handleExport = async (formato, tipo = "auditoria") => {
    setError("");
    try {
      const { filename, sha256 } = await exportAuditFile({ formato, tipo });
      setMensaje(
        `Reporte extraído (${filename}) · SHA-256: ${sha256 ? sha256.slice(0, 16) + "..." : "verificado"}`
      );
    } catch {
      setError("No se pudo extraer el reporte de auditoría.");
    }
  };

  return (
    <div className="space-y-5">
      {mensaje && (
        <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800">
          {mensaje}
        </div>
      )}
      {error && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* VISTA RECEPCION (Req. 108) */}
      {rol === "RECEPCION" && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Check-in de Pacientes (Citas de Hoy)
              </h2>
              <p className="text-xs text-slate-500">
                Establecimiento asignado:{" "}
                <strong>{user.establecimiento_asignado || "Sede Local"}</strong> · Contacto enmascarado
              </p>
            </div>
            <form onSubmit={buscarCheckin} className="flex flex-col sm:flex-row sm:items-start gap-2">
              <div>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={10}
                  required
                  value={cedulaBusqueda}
                  onChange={(e) =>
                    setCedulaBusqueda(e.target.value.replace(/\D/g, "").slice(0, 10))
                  }
                  placeholder="Cédula (ej. 1710000033)"
                  className="px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
                {cedulaBusqueda.length === 10 && (
                  <p
                    className={`text-[11px] mt-1 ${
                      validarCedulaEcuatoriana(cedulaBusqueda)
                        ? "text-emerald-700"
                        : "text-red-600 font-medium"
                    }`}
                  >
                    {validarCedulaEcuatoriana(cedulaBusqueda)
                      ? "✓ Cédula ecuatoriana válida"
                      : "✗ Cédula ecuatoriana inválida"}
                  </p>
                )}
              </div>
              <button
                type="submit"
                disabled={!validarCedulaEcuatoriana(cedulaBusqueda)}
                className="px-4 py-2 text-xs font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
              >
                Consultar Hoy
              </button>
            </form>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-2">Hora</th>
                  <th className="py-2">Paciente</th>
                  <th className="py-2">Contacto Enmascarado</th>
                  <th className="py-2">Especialidad / Médico</th>
                  <th className="py-2 text-right">Asistencia</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {citasRecepcion.map((c) => (
                  <tr key={c.id}>
                    <td className="py-3 font-semibold">{c.hora}</td>
                    <td className="py-3">
                      {c.afiliado_nombre} ({c.afiliado_cedula})
                    </td>
                    <td className="py-3 font-mono text-xs text-slate-600">
                      {c.email_enmascarado} · {c.telefono_enmascarado}
                    </td>
                    <td className="py-3 text-slate-600">
                      {c.especialidad} — {c.medico_nombre}
                    </td>
                    <td className="py-3 text-right">
                      {c.asistencia_confirmada ? (
                        <span className="text-xs px-2.5 py-1 rounded bg-emerald-50 text-emerald-700 font-medium">
                          Confirmada ✓
                        </span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => confirmarAsistenciaRecepcion(c.id)}
                          className="text-xs px-3 py-1 rounded bg-blue-700 text-white hover:bg-blue-800"
                        >
                          Confirmar Asistencia
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {citasRecepcion.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-6 text-center text-xs text-slate-400">
                      {busquedaRealizada
                        ? "No existen citas programadas hoy en su establecimiento para esa cédula."
                        : "Ingrese una cédula para consultar únicamente las citas programadas hoy en su sede."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VISTA MEDICO (Req. 108) */}
      {rol === "MEDICO" && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Agenda Propia de Consultorio (Jornada Actual)
            </h2>
            <p className="text-xs text-slate-500">
              {user.establecimiento_asignado || "Consultorio Asignado"}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-2">Hora</th>
                  <th className="py-2">Cédula</th>
                  <th className="py-2">Paciente</th>
                  <th className="py-2">Especialidad</th>
                  <th className="py-2">Check-in</th>
                  <th className="py-2">Estado</th>
                  <th className="py-2 text-right">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {agendaMedica.map((t) => (
                  <tr key={t.id}>
                    <td className="py-3 font-semibold">{t.hora}</td>
                    <td className="py-3 font-mono text-xs">{t.afiliado_cedula}</td>
                    <td className="py-3">{t.afiliado_nombre}</td>
                    <td className="py-3 text-slate-600">{t.especialidad}</td>
                    <td className="py-3 text-xs">
                      {t.asistencia_confirmada ? (
                        <span className="text-emerald-700 font-medium">En sala</span>
                      ) : (
                        <span className="text-slate-400">Pendiente</span>
                      )}
                    </td>
                    <td className="py-3">
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 font-medium">
                        {t.estado}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      {t.estado === "RESERVADO" && (
                        <button
                          type="button"
                          onClick={() => marcarAtendido(t.id)}
                          className="text-xs px-3 py-1 rounded bg-emerald-700 text-white hover:bg-emerald-800"
                        >
                          Marcar Atendido
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {agendaMedica.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-xs text-slate-400">
                      No tiene pacientes citados para el día de hoy en su consultorio.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VISTA SOPORTE TI (Req. 108, 110, 111, 113, 114) */}
      {rol === "SOPORTE" && (
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-slate-900">
                Estado Técnico y Auditoría Inmutable Sanitizada (AuditLog)
              </h2>
              {auditData.metricas && (
                <p className="text-xs text-slate-500 mt-0.5">
                  Eventos: {auditData.metricas.total_eventos_auditados} · Bloqueos:{" "}
                  {auditData.metricas.intentos_bloqueados_401_403_429} · Sesiones MFA:{" "}
                  {auditData.metricas.sesiones_activas_validadas} · Gateway:{" "}
                  {auditData.metricas.gateway_integracion?.protocolo_transporte} · CB:{" "}
                  {auditData.metricas.circuit_breaker?.estado}
                </p>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={cargarDatosPorRol}
                className="text-xs px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50"
              >
                Actualizar
              </button>
              <button
                type="button"
                onClick={() => handleExport("csv", "auditoria")}
                className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800"
              >
                Extraer Logs CSV
              </button>
              <button
                type="button"
                onClick={() => handleExport("json", "auditoria")}
                className="text-xs px-3 py-1.5 rounded bg-blue-700 text-white hover:bg-blue-800"
              >
                Extraer Logs JSON
              </button>
              <button
                type="button"
                onClick={() => handleExport("csv", "sesiones")}
                className="text-xs px-3 py-1.5 rounded border border-blue-300 text-blue-800 hover:bg-blue-50"
              >
                Extraer Sesiones
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="text-slate-500 border-b border-slate-200">
                <tr>
                  <th className="py-2">Fecha/Hora</th>
                  <th className="py-2">Actor / Rol</th>
                  <th className="py-2">Endpoint</th>
                  <th className="py-2">HTTP</th>
                  <th className="py-2">Payload Sanitizado ([REDACTED])</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {auditData.logs.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2.5 whitespace-nowrap text-slate-500">
                      {new Date(l.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5">
                      {l.usuario_cedula || "anónimo"} ({l.rol || "-"})
                    </td>
                    <td className="py-2.5">
                      {l.metodo} {l.ruta}
                    </td>
                    <td className="py-2.5 font-semibold">{l.status_code}</td>
                    <td className="py-2.5 max-w-md truncate text-slate-700">
                      {JSON.stringify(l.payload_sanitizado)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* VISTA ADMIN (Req. 108, 114) */}
      {rol === "ADMIN" && (
        <div className="space-y-5">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  Métricas Estadísticas Anonimizadas por Especialidad
                </h2>
                <p className="text-xs text-slate-500">
                  Sesiones MFA: {statsAdmin.sesiones_activas_sistema} · Auditorías:{" "}
                  {statsAdmin.total_eventos_auditoria} · Custodia LOPDP:{" "}
                  {statsAdmin.retencion_lopdp_anios} años máx. (IA externa prohibida)
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => handleExport("csv", "auditoria")}
                  className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800"
                >
                  Extraer Auditoría CSV
                </button>
                <button
                  type="button"
                  onClick={() => handleExport("json", "auditoria")}
                  className="text-xs px-3 py-1.5 rounded bg-blue-700 text-white hover:bg-blue-800"
                >
                  Extraer Auditoría JSON
                </button>
                <button
                  type="button"
                  onClick={() => handleExport("csv", "sesiones")}
                  className="text-xs px-3 py-1.5 rounded border border-slate-300 hover:bg-slate-50"
                >
                  Auditoría Sesiones CSV
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {statsAdmin.resumen_especialidades.map((esp) => (
                <div
                  key={esp.especialidad}
                  className="p-4 rounded-xl border border-slate-200 bg-slate-50/60"
                >
                  <div className="text-xs font-medium text-slate-500">{esp.especialidad}</div>
                  <div className="text-2xl font-bold text-slate-900 mt-1">{esp.total}</div>
                  <div className="text-xs text-slate-600 mt-2 flex justify-between">
                    <span>Res: {esp.reservados}</span>
                    <span>Atend: {esp.atendidos}</span>
                    <span>Canc: {esp.cancelados}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Catálogo de Establecimientos + Horarios Médicos */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-5 space-y-3">
              <h3 className="text-sm font-semibold text-slate-900">
                Catálogo de Establecimientos
              </h3>
              <form onSubmit={crearEstablecimiento} className="space-y-2">
                <input
                  type="text"
                  required
                  value={nuevoEstNombre}
                  onChange={(e) => setNuevoEstNombre(e.target.value)}
                  placeholder="Nombre del establecimiento"
                  className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg"
                />
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={nuevoEstCiudad}
                    onChange={(e) => setNuevoEstCiudad(e.target.value)}
                    placeholder="Ciudad"
                    className="w-full px-3 py-2 text-xs border border-slate-300 rounded-lg"
                  />
                  <button
                    type="submit"
                    className="px-3 py-2 text-xs font-medium rounded-lg bg-slate-900 text-white whitespace-nowrap"
                  >
                    + Agregar
                  </button>
                </div>
              </form>
              <ul className="text-xs text-slate-600 space-y-1 pt-1">
                {horariosData.establecimientos.map((eName) => (
                  <li key={eName} className="truncate">
                    • {eName}
                  </li>
                ))}
              </ul>
            </div>

            <div className="lg:col-span-2 bg-white border border-slate-200 rounded-xl shadow-sm p-5 space-y-4">
              <h3 className="text-sm font-semibold text-slate-900">
                Gestión de Horarios y Especialidades
              </h3>
              <form
                onSubmit={crearHorario}
                className="grid grid-cols-1 sm:grid-cols-2 gap-3"
              >
                <select
                  value={nuevoHorario.medico_cedula}
                  onChange={(e) =>
                    setNuevoHorario({ ...nuevoHorario, medico_cedula: e.target.value })
                  }
                  className="px-3 py-2 text-xs border border-slate-300 rounded-lg"
                >
                  {horariosData.medicos.map((m) => (
                    <option key={m.cedula} value={m.cedula}>
                      {m.nombres}
                    </option>
                  ))}
                </select>
                <select
                  value={nuevoHorario.establecimiento}
                  onChange={(e) =>
                    setNuevoHorario({ ...nuevoHorario, establecimiento: e.target.value })
                  }
                  className="px-3 py-2 text-xs border border-slate-300 rounded-lg"
                >
                  {horariosData.establecimientos.map((est) => (
                    <option key={est} value={est}>
                      {est}
                    </option>
                  ))}
                </select>
                <select
                  value={nuevoHorario.especialidad}
                  onChange={(e) =>
                    setNuevoHorario({ ...nuevoHorario, especialidad: e.target.value })
                  }
                  className="px-3 py-2 text-xs border border-slate-300 rounded-lg"
                >
                  {horariosData.especialidades.map((esp) => (
                    <option key={esp} value={esp}>
                      {esp}
                    </option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <input
                    type="time"
                    value={nuevoHorario.hora_inicio}
                    onChange={(e) =>
                      setNuevoHorario({ ...nuevoHorario, hora_inicio: e.target.value })
                    }
                    className="w-full px-2 py-2 text-xs border border-slate-300 rounded-lg"
                  />
                  <input
                    type="time"
                    value={nuevoHorario.hora_fin}
                    onChange={(e) =>
                      setNuevoHorario({ ...nuevoHorario, hora_fin: e.target.value })
                    }
                    className="w-full px-2 py-2 text-xs border border-slate-300 rounded-lg"
                  />
                  <button
                    type="submit"
                    className="px-4 py-2 text-xs font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 whitespace-nowrap"
                  >
                    Guardar
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
