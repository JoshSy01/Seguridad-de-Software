import React, { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import client, { sessionStore, validarCedulaEcuatoriana } from "../api/client";

function contieneFechaNacimiento(password, fechaIso) {
  if (!password || !fechaIso) return false;
  const parts = fechaIso.split("-");
  if (parts.length !== 3) return false;
  const [yyyy, mm, dd] = parts;
  const patrones = [
    `${yyyy}${mm}${dd}`,
    `${dd}${mm}${yyyy}`,
    `${yyyy}-${mm}-${dd}`,
    `${dd}-${mm}-${yyyy}`,
    `${yyyy}/${mm}/${dd}`,
    `${dd}/${mm}/${yyyy}`,
  ];
  return patrones.some((p) => password.includes(p));
}

export default function Login({ onAuthSuccess }) {
  const navigate = useNavigate();
  const location = useLocation();
  const existingUser = sessionStore.getUser();

  const [modo, setModo] = useState("LOGIN"); // LOGIN | REGISTRO
  const [step, setStep] = useState(
    existingUser?.debe_cambiar_clave ? "FORCE_PASSWORD" : "CREDENTIALS"
  );

  // Estado Login
  const [cedula, setCedula] = useState(existingUser?.cedula || "");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [debugOtp, setDebugOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [authUser, setAuthUser] = useState(existingUser || null);

  // Estado Registro ID 102 (Cédula contrastada contra IESS + Correo/Teléfono verificados con OTP)
  const [regStep, setRegStep] = useState("CEDULA"); // CEDULA | DATOS | OTP
  const [regCedula, setRegCedula] = useState("");
  const [regPadron, setRegPadron] = useState(null);
  const [regEmail, setRegEmail] = useState("");
  const [regTelefono, setRegTelefono] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regOtp, setRegOtp] = useState("");
  const [regDebugOtp, setRegDebugOtp] = useState("");

  const [mensaje, setMensaje] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const destinoFinal = (rol) => {
    const intended = location.state?.from;
    if (intended && intended !== "/login") return intended;
    return rol === "AFILIADO" ? "/afiliado" : "/funcionario";
  };

  const validacionClave = useMemo(() => {
    const targetPwd = modo === "REGISTRO" ? regPassword : newPassword;
    const targetDob =
      modo === "REGISTRO" ? regPadron?.fecha_nacimiento : authUser?.fecha_nacimiento;
    const targetCed = modo === "REGISTRO" ? regCedula : authUser?.cedula;

    const largoOk = targetPwd.length >= 12;
    const usaFecha = contieneFechaNacimiento(targetPwd, targetDob);
    const usaCedula = Boolean(targetCed && targetPwd.includes(targetCed));
    return {
      largoOk,
      usaFecha,
      usaCedula,
      esValida: largoOk && !usaFecha && !usaCedula,
    };
  }, [modo, newPassword, authUser, regPassword, regPadron, regCedula]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setMensaje("");
    setLoading(true);
    try {
      const { data } = await client.post("/auth/login/", { cedula, password });
      setDebugOtp(data.debug_otp || "");
      setStep("OTP");
    } catch (err) {
      setError(err.response?.data?.detail || "Error al verificar credenciales.");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await client.post("/auth/verify-otp/", { cedula, otp });
      sessionStore.setSession(data);
      setAuthUser(data.user);
      onAuthSuccess?.(data.user);

      if (data.debe_cambiar_clave) {
        setStep("FORCE_PASSWORD");
      } else {
        navigate(destinoFinal(data.user.rol), { replace: true });
      }
    } catch (err) {
      setError(err.response?.data?.detail || "Código OTP inválido.");
    } finally {
      setLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await client.post("/auth/change-password/", {
        current_password: password || undefined,
        new_password: newPassword,
      });
      const updated = { ...authUser, debe_cambiar_clave: false };
      sessionStore.updateUser(updated);
      setAuthUser(updated);
      onAuthSuccess?.(updated);
      navigate(destinoFinal(updated.rol), { replace: true });
    } catch (err) {
      const resp = err.response?.data;
      const msg =
        resp?.new_password?.[0] ||
        resp?.current_password?.[0] ||
        resp?.detail ||
        "No se pudo actualizar la contraseña.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // Flujo Registro ID 102
  const handleConsultarPadron = async (e) => {
    e.preventDefault();
    setError("");
    setMensaje("");
    setLoading(true);
    try {
      const { data } = await client.post("/auth/registro/consultar-cedula/", {
        cedula: regCedula,
      });
      setRegPadron(data);
      setRegStep("DATOS");
    } catch (err) {
      setError(err.response?.data?.detail || "No se pudo validar la cédula en el IESS.");
    } finally {
      setLoading(false);
    }
  };

  const handleSolicitarOtpRegistro = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await client.post("/auth/registro/solicitar-otp/", {
        cedula: regCedula,
        email: regEmail,
        telefono: regTelefono,
        password: regPassword,
      });
      setRegDebugOtp(data.debug_otp || "");
      setRegStep("OTP");
    } catch (err) {
      const resp = err.response?.data;
      setError(
        resp?.detail ||
          resp?.email?.[0] ||
          resp?.telefono?.[0] ||
          "Revise los datos ingresados."
      );
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmarOtpRegistro = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const { data } = await client.post("/auth/registro/confirmar-otp/", {
        cedula: regCedula,
        otp: regOtp,
      });
      setCedula(regCedula);
      setPassword("");
      setModo("LOGIN");
      setStep("CREDENTIALS");
      setRegStep("CEDULA");
      setRegPadron(null);
      setRegPassword("");
      setRegOtp("");
      setMensaje(data.mensaje || "Cuenta verificada y activada. Inicie sesión.");
    } catch (err) {
      setError(err.response?.data?.detail || "Código OTP inválido.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[75vh] flex items-center justify-center">
      <div className="w-full max-w-md bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        {step !== "FORCE_PASSWORD" && (
          <div className="grid grid-cols-2 border-b border-slate-200 text-xs font-medium">
            <button
              type="button"
              onClick={() => {
                setModo("LOGIN");
                setError("");
                setMensaje("");
              }}
              className={`py-3 ${
                modo === "LOGIN"
                  ? "text-blue-700 border-b-2 border-blue-700 bg-blue-50/40"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              Iniciar Sesión
            </button>
            <button
              type="button"
              onClick={() => {
                setModo("REGISTRO");
                setRegStep("CEDULA");
                setError("");
                setMensaje("");
              }}
              className={`py-3 ${
                modo === "REGISTRO"
                  ? "text-blue-700 border-b-2 border-blue-700 bg-blue-50/40"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              Activar Cuenta Afiliado
            </button>
          </div>
        )}

        <div className="p-6">
          <div className="mb-5">
            <h1 className="text-lg font-semibold text-slate-900">
              Portal Seguro de Turnos · IESS
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {modo === "LOGIN"
                ? "Autenticación multifactor y sesiones verificadas 24/7"
                : "Identificación institucional por cédula y verificación OTP"}
            </p>
          </div>

          {mensaje && (
            <div className="mb-4 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-800">
              {mensaje}
            </div>
          )}

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
              {error}
            </div>
          )}

          {modo === "LOGIN" && step === "CREDENTIALS" && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Número de Cédula Ecuatoriana
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={10}
                  required
                  value={cedula}
                  onChange={(e) => setCedula(e.target.value.replace(/\D/g, "").slice(0, 10))}
                  placeholder="1710000017"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
                {cedula.length === 10 && (
                  <p
                    className={`text-[11px] mt-1 ${
                      validarCedulaEcuatoriana(cedula)
                        ? "text-emerald-700"
                        : "text-red-600 font-medium"
                    }`}
                  >
                    {validarCedulaEcuatoriana(cedula)
                      ? "✓ Cédula ecuatoriana válida (Módulo 10)"
                      : "✗ Cédula ecuatoriana inválida (verifique provincia y dígito verificador)"}
                  </p>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Contraseña
                </label>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>
              <button
                type="submit"
                disabled={loading || !validarCedulaEcuatoriana(cedula)}
                className="w-full py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loading ? "Validando..." : "Continuar"}
              </button>
            </form>
          )}

          {modo === "LOGIN" && step === "OTP" && (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              {debugOtp && (
                <div className="p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-800 flex items-center justify-between">
                  <span>OTP simulado (entorno local):</span>
                  <strong className="font-mono tracking-widest text-sm">{debugOtp}</strong>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Código de verificación MFA (6 dígitos)
                </label>
                <input
                  type="text"
                  maxLength={6}
                  required
                  value={otp}
                  onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  className="w-full px-3 py-2 text-center tracking-[0.4em] font-mono text-base border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
              </div>
              <button
                type="submit"
                disabled={loading || otp.length !== 6}
                className="w-full py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loading ? "Verificando..." : "Verificar e Ingresar"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setStep("CREDENTIALS");
                  setOtp("");
                  setError("");
                }}
                className="w-full py-1.5 text-xs text-slate-500 hover:text-slate-800"
              >
                Volver
              </button>
            </form>
          )}

          {modo === "REGISTRO" && regStep === "CEDULA" && (
            <form onSubmit={handleConsultarPadron} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Número de Cédula Ecuatoriana del Afiliado
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={10}
                  required
                  value={regCedula}
                  onChange={(e) => setRegCedula(e.target.value.replace(/\D/g, "").slice(0, 10))}
                  placeholder="Ej: 1710000058"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                />
                {regCedula.length === 10 && (
                  <p
                    className={`text-[11px] mt-1 ${
                      validarCedulaEcuatoriana(regCedula)
                        ? "text-emerald-700"
                        : "text-red-600 font-medium"
                    }`}
                  >
                    {validarCedulaEcuatoriana(regCedula)
                      ? "✓ Cédula ecuatoriana válida (Módulo 10)"
                      : "✗ Cédula ecuatoriana inválida (verifique provincia y dígito verificador)"}
                  </p>
                )}
                <p className="text-[11px] text-slate-500 mt-1">
                  Se contrastará nombres y fecha de nacimiento con el padrón institucional IESS.
                </p>
              </div>
              <button
                type="submit"
                disabled={loading || !validarCedulaEcuatoriana(regCedula)}
                className="w-full py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loading ? "Consultando padrón IESS..." : "Validar Identidad en IESS"}
              </button>
            </form>
          )}

          {modo === "REGISTRO" && regStep === "DATOS" && regPadron && (
            <form onSubmit={handleSolicitarOtpRegistro} className="space-y-3.5">
              <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs space-y-1">
                <div className="text-slate-500">Identidad contrastada en IESS:</div>
                <div className="font-semibold text-slate-900">{regPadron.nombres}</div>
                <div className="text-slate-600">
                  Cédula: {regPadron.cedula} · Nac.: {regPadron.fecha_nacimiento}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Correo electrónico personal
                </label>
                <input
                  type="email"
                  required
                  value={regEmail}
                  onChange={(e) => setRegEmail(e.target.value)}
                  placeholder="usuario@correo.com"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Teléfono móvil
                </label>
                <input
                  type="text"
                  maxLength={10}
                  required
                  value={regTelefono}
                  onChange={(e) => setRegTelefono(e.target.value.replace(/\D/g, ""))}
                  placeholder="0991234567"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Crear Contraseña Robusta
                </label>
                <input
                  type="password"
                  required
                  value={regPassword}
                  onChange={(e) => setRegPassword(e.target.value)}
                  placeholder="Mínimo 12 caracteres"
                  className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg"
                />
              </div>

              <ul className="text-[11px] space-y-0.5 bg-slate-50 p-2.5 rounded border border-slate-200">
                <li className={validacionClave.largoOk ? "text-emerald-700" : "text-slate-500"}>
                  {validacionClave.largoOk ? "✓" : "•"} Mínimo 12 caracteres
                </li>
                <li className={validacionClave.usaFecha ? "text-red-600 font-medium" : "text-emerald-700"}>
                  {validacionClave.usaFecha
                    ? "✗ Prohibido incluir fecha de nacimiento"
                    : "✓ Sin fecha de nacimiento"}
                </li>
                <li className={validacionClave.usaCedula ? "text-red-600 font-medium" : "text-emerald-700"}>
                  {validacionClave.usaCedula
                    ? "✗ Prohibido incluir número de cédula"
                    : "✓ Sin número de cédula"}
                </li>
              </ul>

              <button
                type="submit"
                disabled={loading || !validacionClave.esValida || regTelefono.length < 9}
                className="w-full py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
              >
                {loading ? "Enviando OTP..." : "Verificar Contacto con OTP"}
              </button>
            </form>
          )}

          {modo === "REGISTRO" && regStep === "OTP" && (
            <form onSubmit={handleConfirmarOtpRegistro} className="space-y-4">
              {regDebugOtp && (
                <div className="p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-800 flex items-center justify-between">
                  <span>OTP verificación correo/móvil:</span>
                  <strong className="font-mono tracking-widest text-sm">{regDebugOtp}</strong>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Código OTP de 6 dígitos
                </label>
                <input
                  type="text"
                  maxLength={6}
                  required
                  value={regOtp}
                  onChange={(e) => setRegOtp(e.target.value.replace(/\D/g, ""))}
                  placeholder="000000"
                  className="w-full px-3 py-2 text-center tracking-[0.4em] font-mono text-base border border-slate-300 rounded-lg"
                />
              </div>
              <button
                type="submit"
                disabled={loading || regOtp.length !== 6}
                className="w-full py-2.5 text-sm font-medium rounded-lg bg-emerald-700 text-white hover:bg-emerald-800 disabled:opacity-50"
              >
                {loading ? "Activando..." : "Confirmar y Activar Cuenta"}
              </button>
            </form>
          )}

          {step === "FORCE_PASSWORD" && (
            <div className="fixed inset-0 bg-slate-900/50 flex items-center justify-center p-4 z-50">
              <div className="bg-white rounded-xl border border-slate-200 max-w-md w-full p-6 shadow-xl">
                <h2 className="text-base font-semibold text-slate-900">
                  Actualización Obligatoria de Contraseña
                </h2>
                <p className="text-xs text-slate-500 mt-1 mb-4">
                  Por seguridad (Req. 107), debe definir una nueva clave personal antes de operar.
                </p>

                {error && (
                  <div className="mb-3 p-2.5 rounded bg-red-50 border border-red-200 text-xs text-red-700">
                    {error}
                  </div>
                )}

                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-slate-700 mb-1">
                      Nueva Contraseña Segura
                    </label>
                    <input
                      type="password"
                      required
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Mínimo 12 caracteres"
                      className="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-600"
                    />
                  </div>

                  <ul className="text-xs space-y-1 bg-slate-50 p-3 rounded-lg border border-slate-200">
                    <li className={validacionClave.largoOk ? "text-emerald-700" : "text-slate-500"}>
                      {validacionClave.largoOk ? "✓" : "•"} Al menos 12 caracteres
                    </li>
                    <li
                      className={
                        validacionClave.usaFecha
                          ? "text-red-600 font-medium"
                          : "text-emerald-700"
                      }
                    >
                      {validacionClave.usaFecha
                        ? "✗ No se permite incluir su fecha de nacimiento"
                        : "✓ Sin fecha de nacimiento"}
                    </li>
                    <li
                      className={
                        validacionClave.usaCedula
                          ? "text-red-600 font-medium"
                          : "text-emerald-700"
                      }
                    >
                      {validacionClave.usaCedula
                        ? "✗ No se permite incluir su número de cédula"
                        : "✓ Sin número de cédula"}
                    </li>
                  </ul>

                  <button
                    type="submit"
                    disabled={loading || !validacionClave.esValida}
                    className="w-full py-2.5 text-sm font-medium rounded-lg bg-blue-700 text-white hover:bg-blue-800 disabled:opacity-50"
                  >
                    {loading ? "Actualizando..." : "Guardar Contraseña"}
                  </button>
                </form>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
