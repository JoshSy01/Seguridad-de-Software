import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export const sessionStore = {
  getAccess: () => sessionStorage.getItem("iess_access_token"),
  getRefresh: () => sessionStorage.getItem("iess_refresh_token"),
  getUser: () => {
    try {
      const raw = sessionStorage.getItem("iess_user");
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  setSession: ({ access, refresh, user, session_id }) => {
    if (access) sessionStorage.setItem("iess_access_token", access);
    if (refresh) sessionStorage.setItem("iess_refresh_token", refresh);
    if (session_id) sessionStorage.setItem("iess_session_id", session_id);
    if (user) sessionStorage.setItem("iess_user", JSON.stringify(user));
  },
  updateUser: (user) => {
    sessionStorage.setItem("iess_user", JSON.stringify(user));
  },
  clear: () => {
    sessionStorage.removeItem("iess_access_token");
    sessionStorage.removeItem("iess_refresh_token");
    sessionStorage.removeItem("iess_session_id");
    sessionStorage.removeItem("iess_user");
  },
};

client.interceptors.request.use((config) => {
  const token = sessionStore.getAccess();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config || {};
    const status = error.response?.status;
    const isAuthRoute =
      originalRequest.url?.includes("/auth/login/") ||
      originalRequest.url?.includes("/auth/verify-otp/") ||
      originalRequest.url?.includes("/auth/refresh/");

    if (status === 401 && !isAuthRoute && !originalRequest._retry) {
      originalRequest._retry = true;
      const refresh = sessionStore.getRefresh();
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE_URL}/auth/refresh/`, {
            refresh,
          });
          sessionStorage.setItem("iess_access_token", data.access);
          originalRequest.headers.Authorization = `Bearer ${data.access}`;
          return client(originalRequest);
        } catch {
          sessionStore.clear();
          window.location.href = "/login";
        }
      } else {
        sessionStore.clear();
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }
      }
    }
    return Promise.reject(error);
  }
);

export function validarCedulaEcuatoriana(cedula) {
  if (typeof cedula !== "string") return false;
  const ced = cedula.trim();
  if (!/^\d{10}$/.test(ced)) return false;
  if (/^(\d)\1{9}$/.test(ced)) return false;

  const provincia = Number(ced.slice(0, 2));
  if (!((provincia >= 1 && provincia <= 24) || provincia === 30)) return false;

  const tercerDigito = Number(ced[2]);
  if (tercerDigito >= 6) return false;

  const coef = [2, 1, 2, 1, 2, 1, 2, 1, 2];
  let suma = 0;
  for (let i = 0; i < 9; i += 1) {
    let valor = Number(ced[i]) * coef[i];
    if (valor >= 10) valor -= 9;
    suma += valor;
  }
  const digitoVerificador = (10 - (suma % 10)) % 10;
  return digitoVerificador === Number(ced[9]);
}

export async function exportAuditFile({ formato = "csv", tipo = "auditoria" }) {
  const response = await client.get("/staff/audit-logs/export/", {
    params: { formato, tipo },
    responseType: "blob",
  });
  const sha256 = response.headers["x-audit-sha256"] || "";
  const disposition = response.headers["content-disposition"] || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : `iess_${tipo}.${formato}`;

  const url = window.URL.createObjectURL(new Blob([response.data]));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
  return { filename, sha256 };
}

export default client;

