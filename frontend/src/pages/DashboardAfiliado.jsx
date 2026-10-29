import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import client, { validarCedulaEcuatoriana } from "../api/client";

function getLocalDateIso(daysOffset = 0) {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + daysOffset);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export default function DashboardAfiliado({ user }) {
  const hoyIso = getLocalDateIso(0);
  const mananaIso = getLocalDateIso(1);
  const defaultFuturaIso = getLocalDateIso(2);
  const maxFechaIso = getLocalDateIso(365);

  const [tab, setTab] = useState("RESERVAR");
  const [delegaciones, setDelegaciones] = useState([]);
  const [beneficiarioCedula, setBeneficiarioCedula] = useState(user?.cedula || "");

  // Catálogo y disponibilidad
  const [establecimientos, setEstablecimientos] = useState([]);
  const [especialidades, setEspecialidades] = useState([]);
  const [establecimiento, setEstablecimiento] = useState("");
  const [especialidad, setEspecialidad] = useState("");
  const [fecha, setFecha] = useState(defaultFuturaIso);
  const [grilla, setGrilla] = useState([]);
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Turnos y notificaciones
  const [turnos, setTurnos] = useState([]);
  const [notificaciones, setNotificaciones] = useState([]);

  // Modal vincular familiar adulto con OTP
  const [linkModal, setLinkModal] = useState(false);
  const [familiarCedula, setFamiliarCedula] = useState("");
  const [familiarOtp, setFamiliarOtp] = useState("");
  const [familiarDebugOtp, setFamiliarDebugOtp] = useState("");
  const [otpSolicitado, setOtpSolicitado] = useState(false);

  // Modal reprogramar con disponibilidad real
  const [reprogTurno, setReprogTurno] = useState(null);
  const [reprogFecha, setReprogFecha] = useState(defaultFuturaIso);
  const [reprogSlots, setReprogSlots] = useState([]);
  const [reprogSelectedSlot, setReprogSelectedSlot] = useState(null);
  const [loadingReprog, setLoadingReprog] = useState(false);

  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");

  const cargarDelegaciones = useCallback(async () => {
    try {
      const { data } = await client.get("/delegaciones/");
      setDelegaciones(data);
    } catch {
      // Silencioso si expira
    }
  }, []);

  const cargarCatalogo = useCallback(async () => {
    try {
      const { data } = await client.get("/turnos/disponibilidad/");
      const estList = data.establecimientos || [];
      const espList = data.especialidades || [];
      setEstablecimientos(estList);
      setEspecialidades(espList);
      if (estList.length) setEstablecimiento((prev) => prev || estList[0]);
      if (espList.length) setEspecialidad((prev) => prev || espList[0]);
    } catch {
      setError("No se pudo cargar el catálogo de atención.");
    }
  }, []);

  const cargarMisTurnos = useCallback(async () => {
    if (!beneficiarioCedula) return;
    try {
      const { data } = await client.get("/turnos/mis-turnos/", {
        params: { beneficiario_cedula: beneficiarioCedula },
      });
      setTurnos(data);
    } catch (err) {
      setError(err.response?.data?.detail || "Error al consultar turnos activos.");
    }
  }, [beneficiarioCedula]);

  const cargarNotificaciones = useCallback(async () => {
    try {
      const { data } = await client.get("/notificaciones/");
      setNotificaciones(data);
    } catch {
      // Silencioso
    }
  }, []);

  const consultarDisponibilidad = useCallback(
    async (est, esp, fec) => {
      if (!est || !esp || !fec) return;
      if (fec < hoyIso) {
        setGrilla([]);
        setSelectedSlot(null);
        setError("No se permite seleccionar fechas pasadas.");
        return;
      }
      setLoadingSlots(true);
      setSelectedSlot(null);
      try {
        const { data } = await client.get("/turnos/disponibilidad/", {
          params: { establecimiento: est, especialidad: esp, fecha: fec },
        });
        setGrilla(data.grilla_turnos || data.horarios_disponibles || []);
      } catch (err) {
        setGrilla([]);
        setError(err.response?.data?.detail || "Error al consultar horarios disponibles.");
      } finally {
        setLoadingSlots(false);
      }
    },
    [hoyIso]
  );

  useEffect(() => {
    cargarDelegaciones();
    cargarCatalogo();
    cargarNotificaciones();
  }, [cargarDelegaciones, cargarCatalogo, cargarNotificaciones]);

  useEffect(() => {
    if (beneficiarioCedula) cargarMisTurnos();
  }, [beneficiarioCedula, cargarMisTurnos]);

  // Carga automática de disponibilidad al cambiar establecimiento, especialidad o fecha futura
  useEffect(() => {
    if (establecimiento && especialidad && fecha && fecha >= hoyIso) {
      consultarDisponibilidad(establecimiento, especialidad, fecha);
    }
  }, [establecimiento, especialidad, fecha, hoyIso, consultarDisponibilidad]);

  // Carga automática de cupos libres en el modal de reprogramación
  useEffect(() => {
    if (!reprogTurno || !reprogFecha || reprogFecha < mananaIso) {
      setReprogSlots([]);
      return;
    }
    setLoadingReprog(true);
    setReprogSelectedSlot(null);
    client
      .get("/turnos/disponibilidad/", {
        params: {
          establecimiento: reprogTurno.establecimiento,
          especialidad: reprogTurno.especialidad,
          fecha: reprogFecha,
        },
      })
      .then(({ data }) => {
        setReprogSlots(data.horarios_disponibles || []);
      })
      .catch(() => setReprogSlots([]))
      .finally(() => setLoadingReprog(false));
  }, [reprogTurno, reprogFecha, mananaIso]);

  const handleFechaChange = (val) => {
    setError("");
    if (val && val < hoyIso) {
      setFecha(hoyIso);
      setError("Las fechas pasadas están bloqueadas; se ajustó al día actual.");
      return;
    }
    setFecha(val);
  };

  const confirmarReserva = async () => {
    if (!selectedSlot || submitting) return;
    setError("");
    setMensaje("");
    setSubmitting(true);
    try {
      await client.post("/turnos/reservar/", {
        beneficiario_cedula: beneficiarioCedula,
        medico_cedula: selectedSlot.medico_cedula,
        establecimiento: selectedSlot.establecimiento,
        especialidad: selectedSlot.especialidad,
        fecha: selectedSlot.fecha,
        hora: selectedSlot.hora,
      });
      setMensaje(
        `Cita reservada exitosamente para el ${selectedSlot.fecha} a las ${selectedSlot.hora}.`
      );
      setSelectedSlot(null);
      await Promise.all([
        consultarDisponibilidad(establecimiento, especialidad, fecha),
        cargarMisTurnos(),
        cargarNotificaciones(),
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo reservar la cita.");
    } finally {
      setSubmitting(false);
    }
  };

  const cancelarTurno = async (id) => {
    if (submitting) return;
    setError("");
    setMensaje("");
    setSubmitting(true);
    try {
      await client.post(`/turnos/${id}/cancelar/`);
      setMensaje("Turno cancelado correctamente.");
      await Promise.all([
        cargarMisTurnos(),
        cargarNotificaciones(),
        consultarDisponibilidad(establecimiento, especialidad, fecha),
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo cancelar el turno.");
    } finally {
      setSubmitting(false);
    }
  };

  const guardarReprogramacion = async (e) => {
    e.preventDefault();
    if (!reprogTurno || !reprogSelectedSlot || submitting) return;
    setError("");
    setMensaje("");
    setSubmitting(true);
    try {
      await client.post(`/turnos/${reprogTurno.id}/reprogramar/`, {
        fecha: reprogFecha,
        hora: reprogSelectedSlot.hora,
        medico_cedula: reprogSelectedSlot.medico_cedula,
      });
      setMensaje(
        `Turno reprogramado para el ${reprogFecha} a las ${reprogSelectedSlot.hora}.`
      );
      setReprogTurno(null);
      await Promise.all([
        cargarMisTurnos(),
        cargarNotificaciones(),
        consultarDisponibilidad(establecimiento, especialidad, fecha),
      ]);
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo reprogramar el turno.");
    } finally {
      setSubmitting(false);
    }
  };

  const abrirModalVincular = () => {
    setError("");
    setMensaje("");
    setLinkModal(true);
    setOtpSolicitado(false);
    setFamiliarCedula("");
    setFamiliarOtp("");
    setFamiliarDebugOtp("");
  };

  const handleSelectorBeneficiario = (val) => {
    setError("");
    setMensaje("");
    if (val === "__ADD_ADULTO__") {
      abrirModalVincular();
      return;
    }
    setBeneficiarioCedula(val);
  };

  const solicitarOtpFamiliar = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const { data } = await client.post("/delegaciones/solicitar/", {
        titular_cedula: familiarCedula,
      });
      setFamiliarDebugOtp(data.debug_otp || "");
      setOtpSolicitado(true);
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo solicitar autorización.");
    }
  };

  const confirmarOtpFamiliar = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const { data } = await client.post("/delegaciones/confirmar-otp/", {
        titular_cedula: familiarCedula,
        otp: familiarOtp,
      });
      await cargarDelegaciones();
      setBeneficiarioCedula(data.delegacion.beneficiario_cedula);
      setLinkModal(false);
      setMensaje("Familiar adulto vinculado mediante OTP.");
    } catch (err) {
      setError(err.response?.data?.detail || "Código OTP inválido.");
    }
  };

  const cuposLibresCount = grilla.filter((s) => s.disponible !== false).length;

  return (
    <div className="space-y-6">
      {/* Selector superior limpio de Titular / Delegación Familiar */}
      <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <label className="text-xs font-medium text-slate-600">
          Gestionando turnos para:
        </label>
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
          <select
            value={beneficiarioCedula}
            onChange={(e) => handleSelectorBeneficiario(e.target.value)}
            className="px-3 py-2 text-sm border border-slate-300 rounded-lg bg-white sm:w-80 focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value={user.cedula}>
              Mi cuenta (Titular) — {user.cedula}
            </option>
            {delegaciones.map((d) => (
              <option key={d.id} value={d.beneficiario_cedula}>
                {d.tipo_vinculo === "HIJO_MENOR"
                  ? `Hijo Menor Registrado — ${d.beneficiario_nombre} (${d.beneficiario_cedula})`
                  : `Adulto Autorizado — ${d.beneficiario_nombre} (${d.beneficiario_cedula})`}
              </option>
            ))}
            <option value="__ADD_ADULTO__">+ Vincular Familiar Adulto con OTP</option>
          </select>
          <button
            type="button"
            onClick={abrirModalVincular}
            className="px-3 py-2 text-xs font-medium rounded-lg border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100 whitespace-nowrap"
          >
            + Vincular Adulto OTP
          </button>
        </div>
      </div>

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

      {/* Tres pestañas operativas simples */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <div className="border-b border-slate-200 flex overflow-x-auto text-sm">
          {[
            { id: "RESERVAR", label: "Reservar Cita" },
            { id: "TURNOS", label: `Mis Turnos (${turnos.filter((t) => t.estado === "RESERVADO").length})` },
            { id: "NOTIFICACIONES", label: `Notificaciones (${notificaciones.length})` },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setTab(t.id);
                setError("");
              }}
              className={`px-5 py-3 font-medium border-b-2 whitespace-nowrap transition-colors ${
                tab === t.id
                  ? "border-blue-700 text-blue-700 bg-blue-50/40"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {tab === "RESERVAR" && (
            <div className="space-y-5">
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Establecimiento
                  </label>
                  <select
                    value={establecimiento}
                    onChange={(e) => setEstablecimiento(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                  >
                    {establecimientos.map((est) => (
                      <option key={est} value={est}>
                        {est}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Especialidad
                  </label>
                  <select
                    value={especialidad}
                    onChange={(e) => setEspecialidad(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                  >
                    {especialidades.map((esp) => (
                      <option key={esp} value={esp}>
                        {esp}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Fecha de atención (hoy o futura)
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="date"
                      min={hoyIso}
                      max={maxFechaIso}
                      value={fecha}
                      onChange={(e) => handleFechaChange(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                    />
                    <button
                      type="button"
                      onClick={() => consultarDisponibilidad(establecimiento, especialidad, fecha)}
                      className="px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-900 text-white hover:bg-slate-800"
                    >
                      Actualizar
                    </button>
                  </div>
                </div>
              </div>

              <div className="pt-2 space-y-3">
                <div className="flex items-center justify-between text-xs text-slate-600">
                  <span>
                    Disponibilidad para <strong>{fecha}</strong>:
                  </span>
                  <span className="font-medium text-emerald-700">
                    {loadingSlots ? "Consultando..." : `${cuposLibresCount} cupos disponibles`}
                  </span>
                </div>

                {loadingSlots ? (
                  <p className="text-xs text-slate-500 py-4">
                    Cargando horarios habilitados...
                  </p>
                ) : grilla.length === 0 ? (
                  <div className="p-4 rounded-lg border border-slate-200 bg-slate-50 text-xs text-slate-600">
                    No quedan horarios habilitados para esta fecha (si es hoy, los horarios previos ya cerraron). Seleccione una fecha futura en el calendario.
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-5 gap-2">
                      {grilla.map((s) => {
                        const libre = s.disponible !== false;
                        const active =
                          libre &&
                          selectedSlot?.hora === s.hora &&
                          selectedSlot?.medico_cedula === s.medico_cedula;
                        return (
                          <button
                            key={`${s.medico_cedula}-${s.hora}`}
                            type="button"
                            disabled={!libre}
                            onClick={() => libre && setSelectedSlot(s)}
                            className={`p-2.5 rounded-lg border text-left text-xs transition ${
                              !libre
                                ? "border-slate-200 bg-slate-100 text-slate-400 cursor-not-allowed"
                                : active
                                ? "border-blue-600 bg-blue-50 text-blue-900 ring-1 ring-blue-600"
                                : "border-slate-200 bg-white hover:border-blue-400"
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-semibold text-sm">{s.hora}</span>
                              <span
                                className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  libre
                                    ? "bg-emerald-50 text-emerald-700"
                                    : "bg-slate-200 text-slate-600"
                                }`}
                              >
                                {libre ? "Libre" : "Ocupado"}
                              </span>
                            </div>
                            <div className="text-slate-500 truncate mt-1">{s.medico_nombre}</div>
                          </button>
                        );
                      })}
                    </div>

                    <div className="pt-2 flex items-center justify-between">
                      <span className="text-xs text-slate-500">
                        {selectedSlot
                          ? `Seleccionado: ${selectedSlot.fecha} a las ${selectedSlot.hora} (${selectedSlot.medico_nombre})`
                          : "Haga clic en un cupo Libre para continuar."}
                      </span>
                      <button
                        type="button"
                        disabled={!selectedSlot || submitting}
                        onClick={confirmarReserva}
                        className="px-5 py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-40"
                      >
                        {submitting ? "Reservando..." : "Confirmar Reserva"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {tab === "TURNOS" && (
            <div>
              {turnos.length === 0 ? (
                <p className="text-sm text-slate-500">
                  No registra turnos para el beneficiario seleccionado.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-slate-500 border-b border-slate-200">
                      <tr>
                        <th className="py-2">Especialidad</th>
                        <th className="py-2">Establecimiento</th>
                        <th className="py-2">Fecha y Hora</th>
                        <th className="py-2">Estado</th>
                        <th className="py-2 text-right">Acciones</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {turnos.map((t) => (
                        <tr key={t.id}>
                          <td className="py-3 font-medium text-slate-900">{t.especialidad}</td>
                          <td className="py-3 text-slate-600">{t.establecimiento}</td>
                          <td className="py-3 text-slate-600">
                            {t.fecha} · {t.hora}
                          </td>
                          <td className="py-3">
                            <span
                              className={`text-xs px-2 py-0.5 rounded font-medium ${
                                t.estado === "RESERVADO"
                                  ? "bg-blue-50 text-blue-700"
                                  : t.estado === "ATENDIDO"
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-slate-100 text-slate-600"
                              }`}
                            >
                              {t.estado}
                            </span>
                          </td>
                          <td className="py-3 text-right space-x-2">
                            {t.estado === "RESERVADO" &&
                              (t.puede_modificar_24h ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setError("");
                                      setReprogTurno(t);
                                      setReprogFecha(
                                        t.fecha >= mananaIso ? t.fecha : defaultFuturaIso
                                      );
                                    }}
                                    className="text-xs px-2.5 py-1 rounded border border-slate-300 hover:bg-slate-50"
                                  >
                                    Reprogramar
                                  </button>
                                  <button
                                    type="button"
                                    disabled={submitting}
                                    onClick={() => cancelarTurno(t.id)}
                                    className="text-xs px-2.5 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50"
                                  >
                                    Cancelar
                                  </button>
                                </>
                              ) : (
                                <span className="text-[11px] text-slate-400">
                                  Menor a 24h (bloqueado)
                                </span>
                              ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {tab === "NOTIFICACIONES" && (
            <div className="space-y-3">
              {notificaciones.length === 0 ? (
                <p className="text-sm text-slate-500">Sin notificaciones recientes.</p>
              ) : (
                notificaciones.map((n) => (
                  <div
                    key={n.id}
                    className="p-3.5 rounded-lg border border-slate-200 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-blue-700">[{n.canal}]</span>
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-medium">
                          Estado: {n.estado_turno}
                        </span>
                      </div>
                      <p className="text-slate-700">{n.mensaje}</p>
                    </div>
                    <Link
                      to={n.enlace_relativo}
                      className="shrink-0 font-mono text-blue-700 hover:underline"
                    >
                      {n.enlace_relativo}
                    </Link>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Modal Vincular Familiar Adulto con OTP */}
      {linkModal && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl border border-slate-200 max-w-sm w-full p-5 shadow-lg">
            <h3 className="text-sm font-semibold text-slate-900 mb-3">
              Vincular Familiar Adulto con OTP
            </h3>
            {!otpSolicitado ? (
              <form onSubmit={solicitarOtpFamiliar} className="space-y-3">
                <div>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={10}
                    required
                    value={familiarCedula}
                    onChange={(e) =>
                      setFamiliarCedula(e.target.value.replace(/\D/g, "").slice(0, 10))
                    }
                    placeholder="Cédula ecuatoriana (ej. 1710000025)"
                    className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                  />
                  {familiarCedula.length === 10 && (
                    <p
                      className={`text-[11px] mt-1 ${
                        validarCedulaEcuatoriana(familiarCedula) &&
                        familiarCedula !== user?.cedula
                          ? "text-emerald-700"
                          : "text-red-600 font-medium"
                      }`}
                    >
                      {familiarCedula === user?.cedula
                        ? "✗ Ingrese la cédula de otro familiar adulto"
                        : validarCedulaEcuatoriana(familiarCedula)
                        ? "✓ Cédula ecuatoriana válida (Módulo 10)"
                        : "✗ Cédula ecuatoriana inválida"}
                    </p>
                  )}
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setLinkModal(false)}
                    className="px-3 py-1.5 text-xs text-slate-600"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={
                      !validarCedulaEcuatoriana(familiarCedula) ||
                      familiarCedula === user?.cedula
                    }
                    className="px-3 py-1.5 text-xs rounded-lg bg-blue-700 text-white disabled:opacity-50"
                  >
                    Enviar OTP al Titular
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={confirmarOtpFamiliar} className="space-y-3">
                {familiarDebugOtp && (
                  <div className="p-2 rounded bg-blue-50 border border-blue-200 text-xs text-blue-800">
                    OTP enviado al titular (simulado): <strong>{familiarDebugOtp}</strong>
                  </div>
                )}
                <input
                  type="text"
                  maxLength={6}
                  required
                  value={familiarOtp}
                  onChange={(e) => setFamiliarOtp(e.target.value.replace(/\D/g, ""))}
                  placeholder="Código OTP de 6 dígitos"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg font-mono"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setLinkModal(false)}
                    className="px-3 py-1.5 text-xs text-slate-600"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={familiarOtp.length !== 6}
                    className="px-3 py-1.5 text-xs rounded-lg bg-blue-700 text-white disabled:opacity-50"
                  >
                    Confirmar Vínculo
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal Reprogramar Turno con Selección Real de Cupos Libres */}
      {reprogTurno && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center p-4 z-50">
          <form
            onSubmit={guardarReprogramacion}
            className="bg-white rounded-xl border border-slate-200 max-w-md w-full p-5 shadow-lg space-y-4"
          >
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Reprogramar Cita · {reprogTurno.especialidad}
              </h3>
              <p className="text-xs text-slate-500">{reprogTurno.establecimiento}</p>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Nueva fecha futura (mínimo 24h de anticipación)
              </label>
              <input
                type="date"
                required
                min={mananaIso}
                max={maxFechaIso}
                value={reprogFecha}
                onChange={(e) => {
                  const val = e.target.value;
                  setReprogFecha(val < mananaIso ? mananaIso : val);
                }}
                className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Seleccione un nuevo horario libre:
              </label>
              {loadingReprog ? (
                <p className="text-xs text-slate-500">Consultando cupos libres...</p>
              ) : reprogSlots.length === 0 ? (
                <p className="text-xs text-slate-500">
                  Sin horarios disponibles en esta fecha. Elija otra fecha futura.
                </p>
              ) : (
                <div className="grid grid-cols-3 gap-2 max-h-44 overflow-y-auto p-1">
                  {reprogSlots.map((s) => {
                    const active = reprogSelectedSlot?.hora === s.hora;
                    return (
                      <button
                        key={`${s.medico_cedula}-${s.hora}`}
                        type="button"
                        onClick={() => setReprogSelectedSlot(s)}
                        className={`py-2 px-2 rounded border text-xs font-medium ${
                          active
                            ? "border-blue-600 bg-blue-50 text-blue-800"
                            : "border-slate-200 hover:border-blue-400"
                        }`}
                      >
                        {s.hora}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setReprogTurno(null)}
                className="px-3 py-1.5 text-xs text-slate-600"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={!reprogSelectedSlot || submitting}
                className="px-4 py-1.5 text-xs font-medium rounded-lg bg-blue-700 text-white disabled:opacity-40"
              >
                {submitting ? "Guardando..." : "Confirmar Nuevo Horario"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
