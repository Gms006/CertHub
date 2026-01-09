import { Fragment, useEffect, useMemo, useState } from "react";

import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { usePreferences } from "../hooks/usePreferences";
import { useToast } from "../hooks/useToast";
import { daysUntil, formatDateTime, parseDnCN } from "../lib/formatters";

type DeviceRead = {
  id: string;
  hostname: string;
  domain?: string | null;
};

type InstalledCert = {
  device_id: string;
  thumbprint: string;
  subject?: string | null;
  issuer?: string | null;
  serial?: string | null;
  not_before?: string | null;
  not_after?: string | null;
  installed_via_agent: boolean;
  cleanup_mode?: "DEFAULT" | "KEEP_UNTIL" | "EXEMPT" | null;
  keep_until?: string | null;
  keep_reason?: string | null;
  job_id?: string | null;
  installed_at?: string | null;
  last_seen_at: string;
  removed_at?: string | null;
};

const formatThumbprint = (value: string, hideLongIds: boolean) =>
  hideLongIds ? value.slice(0, 12) : value;

const formatRetentionLabel = (cert: InstalledCert) => {
  if (!cert.installed_via_agent) {
    return { label: "Não gerenciado", tone: "bg-slate-100 text-slate-600" };
  }
  if (cert.cleanup_mode === "KEEP_UNTIL" && cert.keep_until) {
    return {
      label: `Manter até ${formatDateTime(cert.keep_until)}`,
      tone: "bg-amber-50 text-amber-700",
    };
  }
  if (cert.cleanup_mode === "EXEMPT") {
    return { label: "Manter para sempre", tone: "bg-emerald-50 text-emerald-700" };
  }
  return { label: "Excluir às 18h", tone: "bg-slate-100 text-slate-600" };
};

const InstalledCertsPage = () => {
  const { apiFetch, user } = useAuth();
  const { preferences } = usePreferences();
  const { toast, notify } = useToast();
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [installedCerts, setInstalledCerts] = useState<InstalledCert[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [scope, setScope] = useState<"all" | "agent">("all");
  const [search, setSearch] = useState("");
  const [includeRemoved, setIncludeRemoved] = useState(false);
  const [loading, setLoading] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";

  const loadDevices = async () => {
    try {
      const response = await apiFetch(isAdmin ? "/admin/devices" : "/devices/mine");
      if (!response.ok) {
        notify("Não foi possível carregar devices.", "error");
        return;
      }
      const data = (await response.json()) as DeviceRead[];
      setDevices(data);
    } catch {
      notify("Erro ao carregar devices.", "error");
    }
  };

  const loadInstalledCerts = async () => {
    if (!selectedDeviceId) {
      return;
    }
    setLoading(true);
    try {
      const response = await apiFetch(
        `/devices/${selectedDeviceId}/installed-certs?scope=${scope}&include_removed=${includeRemoved}`,
      );
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível carregar certificados instalados.", "error");
        return;
      }
      const data = (await response.json()) as InstalledCert[];
      setInstalledCerts(data);
    } catch {
      notify("Erro ao carregar certificados instalados.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDevices();
  }, [user?.role_global]);

  useEffect(() => {
    if (!devices.length) return;
    if (selectedDeviceId) return;
    const preferred = preferences.defaultDeviceId;
    const exists = devices.find((device) => device.id === preferred);
    if (exists) {
      setSelectedDeviceId(preferred);
      return;
    }
    setSelectedDeviceId(devices[0].id);
  }, [devices, preferences.defaultDeviceId, selectedDeviceId]);

  useEffect(() => {
    loadInstalledCerts();
  }, [selectedDeviceId, scope, includeRemoved]);

  useEffect(() => {
    if (!selectedDeviceId) return;
    const interval = window.setInterval(() => {
      loadInstalledCerts();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [selectedDeviceId, scope, includeRemoved]);

  const filteredCerts = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return installedCerts;
    return installedCerts.filter((cert) => {
      const subject = cert.subject?.toLowerCase() ?? "";
      const issuer = cert.issuer?.toLowerCase() ?? "";
      const thumbprint = cert.thumbprint.toLowerCase();
      return subject.includes(term) || issuer.includes(term) || thumbprint.includes(term);
    });
  }, [installedCerts, search]);

  const lastUpdated = useMemo(() => {
    const timestamps = installedCerts
      .map((cert) => cert.last_seen_at)
      .filter(Boolean);
    if (!timestamps.length) return "-";
    const latest = timestamps.reduce((max, value) =>
      new Date(value).getTime() > new Date(max).getTime() ? value : max,
    );
    return formatDateTime(latest);
  }, [installedCerts]);

  const toggleRow = (rowKey: string) => {
    setExpandedRows((prev) => ({
      ...prev,
      [rowKey]: !prev[rowKey],
    }));
  };

  const handleCopyThumbprint = async (thumbprint: string) => {
    try {
      await navigator.clipboard.writeText(thumbprint);
      notify("Thumbprint copiado", "success");
    } catch {
      notify("Não foi possível copiar o thumbprint.", "error");
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Instalados</h1>
        <p className="text-sm text-slate-500">
          Inventário do CurrentUser em quase tempo real.
        </p>
      </div>

      <SectionTabs />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-2xl border border-slate-200 bg-slate-50 p-1 text-xs font-semibold text-slate-600">
            <button
              type="button"
              className={`rounded-2xl px-3 py-1 ${scope === "all" ? "bg-white text-slate-900" : ""}`}
              onClick={() => setScope("all")}
            >
              Todos
            </button>
            <button
              type="button"
              className={`rounded-2xl px-3 py-1 ${scope === "agent" ? "bg-white text-slate-900" : ""}`}
              onClick={() => setScope("agent")}
            >
              Somente via Agent
            </button>
          </div>
          <input
            className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
            placeholder="Buscar por subject, issuer ou thumbprint"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <label className="flex items-center gap-2 text-xs text-slate-500">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={includeRemoved}
              onChange={(event) => setIncludeRemoved(event.target.checked)}
            />
            Mostrar removidos
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <select
            className="h-10 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
            value={selectedDeviceId}
            onChange={(event) => setSelectedDeviceId(event.target.value)}
          >
            <option value="">Selecione o device</option>
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.hostname}
              </option>
            ))}
          </select>
          <button
            className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
            onClick={loadInstalledCerts}
          >
            Atualizar
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{filteredCerts.length} certificado(s) encontrados</span>
        <span>Última atualização: {lastUpdated}</span>
      </div>

      {!selectedDeviceId ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Selecione um device para visualizar os certificados instalados.
        </div>
      ) : loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70" />
      ) : filteredCerts.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Nenhum certificado encontrado.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-3xl border border-slate-200 bg-white">
          <table className="w-full min-w-[980px] text-left text-sm">
            <thead className="sticky top-0 z-10 bg-slate-50 text-xs uppercase text-slate-400">
              <tr>
                <th className="w-10 px-4 py-3" />
                <th className="px-4 py-3">Subject</th>
                <th className="px-4 py-3">Issuer</th>
                <th className="px-4 py-3">Validade</th>
                <th className="px-4 py-3">Thumbprint</th>
                <th className="px-4 py-3">Retenção</th>
                <th className="px-4 py-3">Última atualização</th>
              </tr>
            </thead>
            <tbody>
              {filteredCerts.map((cert) => {
                const retention = formatRetentionLabel(cert);
                const rowKey = `${cert.device_id}:${cert.thumbprint}`;
                const subjectCn = parseDnCN(cert.subject);
                const issuerCn = parseDnCN(cert.issuer);
                const validityDays = daysUntil(cert.not_after);
                const isExpired =
                  cert.not_after && new Date(cert.not_after).getTime() < Date.now();
                const validityLabel = cert.not_after
                  ? isExpired
                    ? "Vencido"
                    : validityDays !== null && validityDays <= 30
                      ? `Vence em ${validityDays}d`
                      : "OK"
                  : "-";
                const validityTone = cert.not_after
                  ? isExpired
                    ? "bg-rose-50 text-rose-700"
                    : validityDays !== null && validityDays <= 30
                      ? "bg-amber-50 text-amber-700"
                      : "bg-emerald-50 text-emerald-700"
                  : "bg-slate-100 text-slate-500";
                const isExpanded = expandedRows[rowKey];
                return (
                  <Fragment key={rowKey}>
                    <tr className="border-t border-slate-100">
                      <td className="px-4 py-4 align-top">
                        <button
                          type="button"
                          className="flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 text-slate-500 transition hover:border-slate-300 hover:text-slate-700"
                          onClick={() => toggleRow(rowKey)}
                          aria-label={isExpanded ? "Recolher detalhes" : "Expandir detalhes"}
                        >
                          <span className={`text-xs transition ${isExpanded ? "rotate-180" : ""}`}>
                            ▾
                          </span>
                        </button>
                      </td>
                      <td className="px-4 py-4 text-slate-700">
                        <div className="max-w-[320px] space-y-1">
                          <div className="truncate text-sm font-semibold text-slate-900">
                            {subjectCn}
                          </div>
                          <div
                            className="line-clamp-2 text-xs text-slate-400"
                            title={cert.subject ?? "-"}
                          >
                            {cert.subject ?? "-"}
                          </div>
                        </div>
                        {cert.removed_at ? (
                          <span className="mt-2 block text-[11px] text-rose-500">
                            Removido em {formatDateTime(cert.removed_at)}
                          </span>
                        ) : null}
                      </td>
                      <td className="px-4 py-4 text-slate-600">
                        <div className="max-w-[260px] space-y-1">
                          <div className="truncate text-sm font-semibold text-slate-800">
                            {issuerCn}
                          </div>
                          <div
                            className="line-clamp-2 text-xs text-slate-400"
                            title={cert.issuer ?? "-"}
                          >
                            {cert.issuer ?? "-"}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-slate-600">
                        <div className="space-y-1">
                          <div className="text-sm text-slate-700">
                            {formatDateTime(cert.not_after)}
                          </div>
                          <span
                            className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${validityTone}`}
                          >
                            {validityLabel}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-4 text-slate-500">
                        <div className="flex flex-col gap-2">
                          <span
                            className="font-mono text-xs text-slate-600"
                            title={cert.thumbprint}
                          >
                            {formatThumbprint(cert.thumbprint, preferences.hideLongIds)}
                          </span>
                          <button
                            type="button"
                            className="w-fit text-xs font-semibold text-slate-500 underline-offset-4 transition hover:text-slate-700 hover:underline"
                            onClick={() => handleCopyThumbprint(cert.thumbprint)}
                          >
                            Copiar
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-4">
                        <span
                          className={`inline-flex max-w-[200px] items-center rounded-full px-3 py-1 text-xs font-semibold ${retention.tone}`}
                          title={retention.label}
                        >
                          {retention.label}
                        </span>
                      </td>
                      <td className="px-4 py-4 text-slate-500">
                        {formatDateTime(cert.last_seen_at)}
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr className="border-t border-slate-100 bg-slate-50/60">
                        <td colSpan={7} className="px-4 py-4 text-xs text-slate-600">
                          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">Serial</div>
                              <div className="mt-1 font-mono text-sm text-slate-700">
                                {cert.serial ?? "-"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">
                                Not Before
                              </div>
                              <div className="mt-1 text-sm text-slate-700">
                                {formatDateTime(cert.not_before)}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">Not After</div>
                              <div className="mt-1 text-sm text-slate-700">
                                {formatDateTime(cert.not_after)}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">
                                Instalado em
                              </div>
                              <div className="mt-1 text-sm text-slate-700">
                                {formatDateTime(cert.installed_at)}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">Job ID</div>
                              <div className="mt-1 font-mono text-sm text-slate-700">
                                {cert.job_id ?? "-"}
                              </div>
                            </div>
                            <div>
                              <div className="text-[11px] uppercase text-slate-400">
                                Motivo retenção
                              </div>
                              <div className="mt-1 text-sm text-slate-700">
                                {cert.keep_reason ?? "-"}
                              </div>
                            </div>
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
};

export default InstalledCertsPage;
