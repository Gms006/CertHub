import { useEffect, useMemo, useState } from "react";

import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { formatDate } from "../lib/formatters";

type InstallJobRead = {
  id: string;
  cert_id: string;
  device_id: string;
  requested_by_user_id: string;
  status: string;
  created_at: string;
  updated_at: string;
};

type CertificateRead = {
  id: string;
  name: string;
};

type DeviceRead = {
  id: string;
  hostname: string;
};

const statusStyles: Record<string, string> = {
  REQUESTED: "bg-amber-50 text-amber-700",
  PENDING: "bg-sky-50 text-sky-700",
  IN_PROGRESS: "bg-indigo-50 text-indigo-700",
  DONE: "bg-emerald-50 text-emerald-700",
  FAILED: "bg-rose-50 text-rose-700",
  EXPIRED: "bg-slate-100 text-slate-600",
  CANCELED: "bg-slate-100 text-slate-600",
};

const statusLabels: Record<string, string> = {
  REQUESTED: "Solicitado",
  PENDING: "Pendente",
  IN_PROGRESS: "Em progresso",
  DONE: "Concluído",
  FAILED: "Falhou",
  EXPIRED: "Expirado",
  CANCELED: "Cancelado",
};

const JobsPage = () => {
  const { apiFetch, user } = useAuth();
  const { toast, notify } = useToast();
  const [jobs, setJobs] = useState<InstallJobRead[]>([]);
  const [certificates, setCertificates] = useState<CertificateRead[]>([]);
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [loading, setLoading] = useState(true);

  const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";
  const isView = user?.role_global === "VIEW";

  const loadJobs = async () => {
    setLoading(true);
    try {
      const endpoint = isAdmin
        ? "/install-jobs"
        : isView
          ? "/install-jobs/my-device"
          : "/install-jobs/mine";
      const response = await apiFetch(endpoint);
      if (!response.ok) {
        notify("Não foi possível carregar jobs.", "error");
        return;
      }
      const data = (await response.json()) as InstallJobRead[];
      setJobs(data);
    } catch {
      notify("Erro ao carregar jobs.", "error");
    } finally {
      setLoading(false);
    }
  };

  const loadReferences = async () => {
    try {
      const [certResponse, deviceResponse] = await Promise.all([
        apiFetch("/certificados"),
        apiFetch("/admin/devices"),
      ]);
      if (certResponse.ok) {
        setCertificates((await certResponse.json()) as CertificateRead[]);
      }
      if (deviceResponse.ok) {
        setDevices((await deviceResponse.json()) as DeviceRead[]);
      }
    } catch {
      // silencioso
    }
  };

  useEffect(() => {
    loadJobs();
    loadReferences();
  }, [isAdmin]);

  const certMap = useMemo(
    () => new Map(certificates.map((cert) => [cert.id, cert.name])),
    [certificates],
  );
  const deviceMap = useMemo(
    () => new Map(devices.map((device) => [device.id, device.hostname])),
    [devices],
  );

  const handleApprove = async (jobId: string, approve: boolean) => {
    try {
      const response = await apiFetch(
        `/install-jobs/${jobId}/${approve ? "approve" : "deny"}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        },
      );
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível atualizar o job.", "error");
        return;
      }
      notify(approve ? "Job aprovado." : "Job negado.");
      loadJobs();
    } catch {
      notify("Erro ao atualizar job.", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Jobs</h1>
        <p className="text-sm text-slate-500">
          Controle de instalações com aprovação e acompanhamento em tempo real.
        </p>
      </div>

      <SectionTabs />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-slate-200 bg-white p-4">
        <p className="text-sm text-slate-500">
          {jobs.length} jobs encontrados
        </p>
        <button
          className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          onClick={loadJobs}
        >
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70" />
      ) : jobs.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Nenhum job encontrado.
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Certificado</th>
                <th className="px-4 py-3">Device</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Criado</th>
                <th className="px-4 py-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-t border-slate-100">
                  <td className="px-4 py-4">
                    <p className="font-medium text-slate-800">
                      {certMap.get(job.cert_id) ?? job.cert_id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-slate-400">{job.requested_by_user_id}</p>
                  </td>
                  <td className="px-4 py-4 text-slate-600">
                    {deviceMap.get(job.device_id) ?? job.device_id.slice(0, 8)}
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${
                        statusStyles[job.status] ?? "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {statusLabels[job.status] ?? job.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-slate-500">
                    {formatDate(job.created_at)}
                  </td>
                  <td className="px-4 py-4 text-right">
                    {isAdmin && job.status === "REQUESTED" ? (
                      <div className="flex justify-end gap-2">
                        <button
                          className="h-9 rounded-2xl border border-slate-200 px-3 text-xs text-slate-600"
                          onClick={() => handleApprove(job.id, false)}
                        >
                          Negar
                        </button>
                        <button
                          className="h-9 rounded-2xl bg-[#0e2659] px-3 text-xs font-semibold text-white"
                          onClick={() => handleApprove(job.id, true)}
                        >
                          Aprovar
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">Sem ações</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
};

export default JobsPage;
