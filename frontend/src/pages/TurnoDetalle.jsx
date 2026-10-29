import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import client from "../api/client";

export default function TurnoDetalle() {
  const { id } = useParams();
  const [turno, setTurno] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    client
      .get(`/turnos/${id}/`)
      .then(({ data }) => setTurno(data))
      .catch((err) => {
        setError(
          err.response?.data?.detail ||
            "No tiene autorización para visualizar el detalle de este turno."
        );
      })
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <div className="max-w-lg mx-auto bg-white border border-slate-200 rounded-xl shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-base font-semibold text-slate-900">
          Comprobante de Cita Médica #{id}
        </h2>
        <Link to="/afiliado" className="text-xs text-blue-700 hover:underline">
          ← Volver al panel
        </Link>
      </div>

      {loading && <p className="text-sm text-slate-500">Cargando detalle seguro...</p>}

      {error && (
        <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
          {error}
        </div>
      )}

      {turno && (
        <dl className="divide-y divide-slate-100 text-sm">
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Beneficiario</dt>
            <dd className="font-medium text-slate-900">{turno.afiliado_nombre}</dd>
          </div>
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Establecimiento</dt>
            <dd className="font-medium text-slate-900">{turno.establecimiento}</dd>
          </div>
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Especialidad</dt>
            <dd className="font-medium text-slate-900">{turno.especialidad}</dd>
          </div>
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Profesional</dt>
            <dd className="font-medium text-slate-900">{turno.medico_nombre}</dd>
          </div>
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Fecha y Hora</dt>
            <dd className="font-medium text-slate-900">
              {turno.fecha} · {turno.hora}
            </dd>
          </div>
          <div className="py-2.5 flex justify-between">
            <dt className="text-slate-500">Estado</dt>
            <dd className="font-semibold text-blue-700">{turno.estado}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

