import React, { useEffect, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import client, { sessionStore } from "./api/client";
import Login from "./pages/Login";
import DashboardAfiliado from "./pages/DashboardAfiliado";
import DashboardFuncionario from "./pages/DashboardFuncionario";
import TurnoDetalle from "./pages/TurnoDetalle";

function AuthGuard({ children, allowedRoles }) {
  const location = useLocation();
  const token = sessionStore.getAccess();
  const user = sessionStore.getUser();

  if (!token || !user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (user.debe_cambiar_clave) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.rol)) {
    const fallback = user.rol === "AFILIADO" ? "/afiliado" : "/funcionario";
    return <Navigate to={fallback} replace />;
  }

  return children;
}

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [user, setUser] = useState(() => sessionStore.getUser());
  const [sessionsModal, setSessionsModal] = useState(false);
  const [activeSessions, setActiveSessions] = useState([]);

  useEffect(() => {
    const token = sessionStore.getAccess();
    if (!token) {
      setUser(null);
      return;
    }
    client
      .get("/auth/me/")
      .then(({ data }) => {
        sessionStore.updateUser(data.user);
        setUser(data.user);
      })
      .catch(() => {
        sessionStore.clear();
        setUser(null);
      });
  }, [location.pathname]);

  const handleLogout = async () => {
    try {
      await client.post("/auth/logout/");
    } catch {
      // Ignorar si ya expiró
    } finally {
      sessionStore.clear();
      setUser(null);
      navigate("/login", { replace: true });
    }
  };

  const openSessionsModal = async () => {
    try {
      const { data } = await client.get("/auth/sessions/");
      setActiveSessions(data);
      setSessionsModal(true);
    } catch {
      setSessionsModal(false);
    }
  };

  const revokeSession = async (id, esActual) => {
    if (esActual) {
      await handleLogout();
      return;
    }
    await client.delete(`/auth/sessions/${id}/`);
    const { data } = await client.get("/auth/sessions/");
    setActiveSessions(data);
  };

  const showNavbar = user && !user.debe_cambiar_clave && location.pathname !== "/login";

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      {showNavbar && (
        <header className="bg-white border-b border-slate-200">
          <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-semibold text-slate-900 tracking-tight">
                IESS · Turnos Seguros
              </span>
              <span className="text-xs font-medium px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                {user.rol}
              </span>
            </div>
            <div className="flex items-center gap-3 text-sm">
              <span className="text-slate-600 hidden sm:inline">{user.nombres}</span>
              <button
                type="button"
                onClick={openSessionsModal}
                className="text-xs px-2.5 py-1 rounded border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
              >
                Sesiones MFA
              </button>
              <button
                type="button"
                onClick={handleLogout}
                className="text-xs px-3 py-1.5 rounded bg-slate-900 text-white hover:bg-slate-800"
              >
                Cerrar sesión
              </button>
            </div>
          </div>
        </header>
      )}

      <main className="flex-1 max-w-5xl w-full mx-auto px-4 py-8">
        <Routes>
          <Route path="/login" element={<Login onAuthSuccess={setUser} />} />
          <Route
            path="/afiliado"
            element={
              <AuthGuard allowedRoles={["AFILIADO"]}>
                <DashboardAfiliado user={user} />
              </AuthGuard>
            }
          />
          <Route
            path="/funcionario"
            element={
              <AuthGuard allowedRoles={["RECEPCION", "MEDICO", "SOPORTE", "ADMIN"]}>
                <DashboardFuncionario user={user} />
              </AuthGuard>
            }
          />
          <Route
            path="/turnos/detalle/:id"
            element={
              <AuthGuard allowedRoles={["AFILIADO"]}>
                <TurnoDetalle />
              </AuthGuard>
            }
          />
          <Route
            path="*"
            element={
              user && !user.debe_cambiar_clave ? (
                <Navigate to={user.rol === "AFILIADO" ? "/afiliado" : "/funcionario"} replace />
              ) : (
                <Navigate to="/login" replace />
              )
            }
          />
        </Routes>
      </main>

      {sessionsModal && (
        <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-lg border border-slate-200 max-w-lg w-full p-5 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-slate-900 text-sm">
                Sesiones Validadas Activas
              </h3>
              <button
                type="button"
                onClick={() => setSessionsModal(false)}
                className="text-xs text-slate-500 hover:text-slate-800"
              >
                Cerrar
              </button>
            </div>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {activeSessions.map((s) => (
                <div
                  key={s.id}
                  className="p-3 rounded border border-slate-200 flex items-center justify-between text-xs"
                >
                  <div>
                    <div className="font-medium text-slate-800">
                      IP: {s.ip || "Local"}{" "}
                      {s.es_actual && (
                        <span className="ml-1 text-emerald-700 font-semibold">(Actual)</span>
                      )}
                    </div>
                    <div className="text-slate-500">
                      Última actividad: {new Date(s.ultima_actividad).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => revokeSession(s.id, s.es_actual)}
                    className="px-2 py-1 rounded border border-red-200 text-red-700 hover:bg-red-50"
                  >
                    Revocar
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

