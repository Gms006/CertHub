import { Download } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { usePreferences } from "../hooks/usePreferences";
import { useToast } from "../hooks/useToast";
import { formatDateTime, sanitizeSensitiveLabel } from "../lib/formatters";

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
  REQUESTED: "bg-amber-50 text-amber-700 ring-1 ring-amber-200/70",
  PENDING: "bg-sky-50 text-sky-700 ring-1 ring-sky-200/70",
  IN_PROGRESS: "bg-indigo-50 text-indigo-700 ring-1 ring-indigo-200/70",
  DONE: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/70",
  FAILED: "bg-rose-50 text-rose-700 ring-1 ring-rose-200/70",
  EXPIRED: "bg-slate-100 text-slate-600 ring-1 ring-slate-200/70",
  CANCELED: "bg-rose-50 text-rose-700 ring-1 ring-rose-200/70",
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
  const { preferences } = usePreferences();
  const { toast, notify } = useToast();
  const [jobs, setJobs] = useState<InstallJobRead[]>([]);
  const [certificates, setCertificates] = useState<CertificateRead[]>([]);
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [deviceFilter, setDeviceFilter] = useState("Todos");
  const [exportPeriod, setExportPeriod] = useState("last_15_days");
  const [statusFilter, setStatusFilter] = useState<
    "all" | "pending" | "done" | "error"
  >("all");
  const [search, setSearch] = useState("");

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
      const certResponse = await apiFetch("/certificados");
      const deviceResponse = isAdmin
        ? await apiFetch("/admin/devices")
        : await apiFetch("/devices/mine");
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
  }, [user?.role_global]);

  useEffect(() => {
    if (!preferences.autoRefreshJobs) return;
    const interval = window.setInterval(() => {
      loadJobs();
    }, 20000);
    return () => window.clearInterval(interval);
  }, [preferences.autoRefreshJobs, user?.role_global]);

  const certMap = useMemo(
    () =>
      new Map(
        certificates.map((cert) => [cert.id, sanitizeSensitiveLabel(cert.name)]),
      ),
    [certificates],
  );
  const deviceMap = useMemo(
    () => new Map(devices.map((device) => [device.id, device.hostname])),
    [devices],
  );

  const filteredJobs = useMemo(() => {
    let result = jobs;
    if (isAdmin && deviceFilter !== "Todos") {
      result = result.filter((job) => job.device_id === deviceFilter);
    }
    if (statusFilter !== "all") {
      const statusGroups: Record<"pending" | "done" | "error", string[]> = {
        pending: ["REQUESTED", "PENDING", "IN_PROGRESS"],
        done: ["DONE"],
        error: ["FAILED", "EXPIRED", "CANCELED"],
      };
      const allowed = statusGroups[statusFilter];
      result = result.filter((job) => allowed.includes(job.status));
    }
    const term = search.trim().toLowerCase();
    if (!term) return result;
    return result.filter((job) => {
      const certName = certMap.get(job.cert_id)?.toLowerCase() ?? "";
      const deviceName = deviceMap.get(job.device_id)?.toLowerCase() ?? "";
      return (
        certName.includes(term) ||
        job.id.toLowerCase().includes(term) ||
        job.device_id.toLowerCase().includes(term) ||
        deviceName.includes(term)
      );
    });
  }, [deviceFilter, isAdmin, jobs, statusFilter, search, certMap, deviceMap]);

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

  const formatId = (value: string) =>
    preferences.hideLongIds ? value.slice(0, 8) : value;

  const parseFileName = (contentDisposition: string | null) => {
    if (!contentDisposition) return null;
    const match = /filename="([^"]+)"/.exec(contentDisposition);
    return match?.[1] ?? null;
  };

  const handleExport = async () => {
    try {
      const scope = isAdmin ? "all" : isView ? "my-device" : "mine";
      const response = await apiFetch(
        `/install-jobs/export?period=${exportPeriod}&scope=${scope}`,
      );
      if (!response.ok) {
        notify("Não foi possível exportar os jobs.", "error");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const fileName =
        parseFileName(response.headers.get("content-disposition")) ??
        "jobs.xlsx";
      link.href = url;
      link.download = fileName;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      notify("Erro ao exportar os jobs.", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Solicitações</h1>
        <p className="text-sm text-slate-500">
          Controle de instalações com aprovação e acompanhamento em tempo real.
        </p>
      </div>

      <SectionTabs />

      <div className="flex flex-wrap gap-3 rounded-3xl border border-slate-200 bg-white p-4">
        <select
          className="h-10 flex-1 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as "all" | "pending" | "done" | "error")
          }
        >
          <option value="all">Todos</option>
          <option value="pending">Pendentes</option>
          <option value="done">Concluídos</option>
          <option value="error">Erro</option>
        </select>
        <input
          className="h-10 flex-[2] rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          placeholder="Buscar por certificado, job id, device..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          className="h-10 flex-1 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
          value={exportPeriod}
          onChange={(event) => setExportPeriod(event.target.value)}
        >
          <option value="last_15_days">Últimos 15 dias</option>
          <option value="this_month">Este mês</option>
          <option value="last_6_months">Últimos 6 meses</option>
        </select>
        {isAdmin ? (
          <select
            className="h-10 flex-1 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
            value={deviceFilter}
            onChange={(event) => setDeviceFilter(event.target.value)}
          >
            <option value="Todos">Todos os devices</option>
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.hostname}
              </option>
            ))}
          </select>
        ) : null}
        <button
          className="flex h-10 items-center gap-2 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          onClick={handleExport}
        >
          <Download className="h-4 w-4" />
          Exportar Excel
        </button>
        <button
          className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          onClick={loadJobs}
        >
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70" />
      ) : filteredJobs.length === 0 ? (
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
                <th className="px-4 py-3">Criado em</th>
                <th className="px-4 py-3 text-right">Erros</th>
              </tr>
            </thead>
            <tbody>
              {filteredJobs.map((job) => (
                <tr key={job.id} className="border-t border-slate-100">
                  <td className="px-4 py-4">
                    <div className="max-w-[220px] space-y-1">
                      <p
                        className="truncate font-medium text-slate-900"
                        title={certMap.get(job.cert_id) ?? job.cert_id}
                      >
                        {certMap.get(job.cert_id) ?? formatId(job.cert_id)}
                      </p>
                      <p className="truncate text-xs text-slate-500">
                        Job {formatId(job.id)} •{" "}
                        {formatId(job.requested_by_user_id)}
                      </p>
                    </div>
                  </td>
                  <td className="px-4 py-4 text-slate-600">
                    <span
                      className="inline-block max-w-[160px] truncate"
                      title={deviceMap.get(job.device_id) ?? job.device_id}
                    >
                      {deviceMap.get(job.device_id) ?? formatId(job.device_id)}
                    </span>
                  </td>
                  <td className="px-4 py-4">
                    <span
                      className={`inline-flex max-w-[160px] items-center whitespace-nowrap truncate rounded-full px-3 py-1 text-xs font-semibold ${
                        statusStyles[job.status] ??
                        "bg-slate-100 text-slate-600 ring-1 ring-slate-200/70"
                      }`}
                      title={statusLabels[job.status] ?? job.status}
                    >
                      {statusLabels[job.status] ?? job.status}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-slate-500">
                    {formatDateTime(job.created_at)}
                  </td>
                  <td className="px-4 py-4 text-right">
                    <details className="relative inline-block text-left">
                      <summary className="list-none rounded-full border border-slate-200 px-2 py-1 text-sm text-slate-600 transition hover:border-slate-300 hover:text-slate-800">
                        ⋯
                      </summary>
                      <div className="absolute right-0 z-10 mt-2 w-40 rounded-2xl border border-slate-200 bg-white p-2 text-xs text-slate-600 shadow-lg">
                        {job.status === "FAILED" ? (
                          <span className="block px-2 py-1 text-rose-600">
                            Erro registrado
                          </span>
                        ) : (
                          <span className="block px-2 py-1 text-slate-500">
                            Sem erros
                          </span>
                        )}
                        {isAdmin && job.status === "REQUESTED" ? (
                          <div className="mt-2 flex flex-col gap-2">
                            <button
                              className="rounded-full border border-slate-200/70 px-3 py-1 text-xs text-slate-600"
                              onClick={() => handleApprove(job.id, false)}
                            >
                              Negar
                            </button>
                            <button
                              className="rounded-full bg-[#0e2659] px-3 py-1 text-xs font-semibold text-white"
                              onClick={() => handleApprove(job.id, true)}
                            >
                              Aprovar
                            </button>
                          </div>
                        ) : null}
                      </div>
                    </details>
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
