import { Filter, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { usePreferences } from "../hooks/usePreferences";
import { useToast } from "../hooks/useToast";
import { formatDateTime } from "../lib/formatters";

type AuditLogRead = {
  id: string;
  timestamp: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  actor_label?: string | null;
  meta_json?: Record<string, unknown> | null;
};

const getJobId = (audit: AuditLogRead) => {
  const metaJobId = audit.meta_json?.job_id;
  if (typeof metaJobId === "string") {
    return metaJobId;
  }
  if (audit.entity_type.toLowerCase() === "install_job") {
    return audit.entity_id ?? undefined;
  }
  return undefined;
};

const AuditPage = () => {
  const { apiFetch } = useAuth();
  const { preferences } = usePreferences();
  const { toast, notify } = useToast();
  const [audits, setAudits] = useState<AuditLogRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");

  const loadAudit = async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/audit");
      if (!response.ok) {
        notify("Não foi possível carregar auditoria.", "error");
        return;
      }
      const data = (await response.json()) as AuditLogRead[];
      setAudits(data);
    } catch {
      notify("Erro ao carregar auditoria.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAudit();
  }, []);

  useEffect(() => {
    if (!preferences.autoRefreshAudit) return;
    const interval = window.setInterval(() => {
      loadAudit();
    }, 20000);
    return () => window.clearInterval(interval);
  }, [preferences.autoRefreshAudit]);

  const uniqueActions = useMemo(
    () =>
      Array.from(new Set(audits.map((a) => a.action)))
        .sort()
        .filter((action) => action.trim().length > 0),
    [audits],
  );

  const uniqueActors = useMemo(
    () =>
      Array.from(
        new Set(
          audits
            .map((a) => a.actor_label)
            .filter((a): a is string => a != null && a.trim().length > 0),
        ),
      ).sort(),
    [audits],
  );

  const filteredAudits = useMemo(() => {
    return audits.filter((audit) => {
      const actionOk = actionFilter
        ? audit.action === actionFilter
        : true;
      const actorOk = actorFilter
        ? audit.actor_label === actorFilter
        : true;
      return actionOk && actorOk;
    });
  }, [actionFilter, actorFilter, audits]);

  const lastUpdated = useMemo(() => {
    const timestamps = audits.map((audit) => audit.timestamp).filter(Boolean);
    if (!timestamps.length) return "-";
    const latest = timestamps.reduce((max, value) =>
      new Date(value).getTime() > new Date(max).getTime() ? value : max,
    );
    return formatDateTime(latest);
  }, [audits]);

  const formatShortId = (value: string) =>
    preferences.hideLongIds ? value.slice(0, 8) : value;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Auditoria</h1>
        <p className="text-sm text-slate-500">
          Acompanhe ações críticas realizadas no portal e no Agent.
        </p>
      </div>

      <SectionTabs />

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-3xl bg-white/70 p-4 shadow-sm ring-1 ring-slate-200/70 backdrop-blur">
        <div className="flex flex-1 flex-wrap items-center gap-3">
          <div className="relative flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600">
              <Filter className="h-4 w-4" />
            </span>
            <select
              className="h-10 w-full rounded-2xl bg-white pl-9 pr-4 text-sm text-slate-900 ring-1 ring-slate-200/70 transition focus:ring-2 focus:ring-slate-300 appearance-none"
              value={actionFilter}
              onChange={(event) => setActionFilter(event.target.value)}
            >
              <option value="">Todas as ações</option>
              {uniqueActions.map((action) => (
                <option key={action} value={action}>
                  {action}
                </option>
              ))}
            </select>
          </div>
          <div className="relative flex-1">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-600">
              <Filter className="h-4 w-4" />
            </span>
            <select
              className="h-10 w-full rounded-2xl bg-white pl-9 pr-4 text-sm text-slate-900 ring-1 ring-slate-200/70 transition focus:ring-2 focus:ring-slate-300 appearance-none"
              value={actorFilter}
              onChange={(event) => setActorFilter(event.target.value)}
            >
              <option value="">Todos os atores</option>
              {uniqueActors.map((actor) => (
                <option key={actor} value={actor}>
                  {actor}
                </option>
              ))}
            </select>
          </div>
        </div>
        <button
          className="flex h-10 items-center gap-2 rounded-2xl bg-white/70 px-4 text-sm font-medium text-slate-700 shadow-sm ring-1 ring-slate-200/70 transition hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 whitespace-nowrap"
          onClick={loadAudit}
        >
          <RefreshCw className="h-4 w-4 shrink-0" />
          Atualizar
        </button>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>{filteredAudits.length} registros encontrados</span>
        <span>Última atualização: {lastUpdated}</span>
      </div>

      {loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200/70 bg-white/70 shadow-sm ring-1 ring-slate-200/70" />
      ) : filteredAudits.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200/70 bg-white/70 p-10 text-center text-sm text-slate-500 shadow-sm ring-1 ring-slate-200/70">
          Nenhum registro de auditoria encontrado.
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl bg-white/70 shadow-sm ring-1 ring-slate-200/70 backdrop-blur">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Ator</th>
                <th className="px-4 py-3">Ação</th>
                <th className="px-4 py-3">Job</th>
                <th className="px-4 py-3">Entidade</th>
                <th className="px-4 py-3">Detalhes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200/70">
              {filteredAudits.map((audit) => {
                const jobId = getJobId(audit);
                return (
                  <tr
                    key={audit.id}
                    className="odd:bg-white even:bg-slate-50/40 hover:bg-slate-100/60"
                  >
                    <td className="px-4 py-4 text-slate-500">
                      {formatDateTime(audit.timestamp)}
                    </td>
                    <td className="px-4 py-4 text-slate-700">
                      <span
                        className="block max-w-[180px] truncate"
                        title={audit.actor_label ?? "-"}
                      >
                        {audit.actor_label ?? "-"}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span
                        className="inline-flex max-w-[220px] items-center whitespace-nowrap truncate rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600"
                        title={audit.action}
                      >
                        {audit.action}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-slate-600">
                      {jobId ? (
                        <div className="space-y-1">
                          <span
                            className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700"
                            title={jobId}
                          >
                            {formatShortId(jobId)}
                          </span>
                          <p className="text-[11px] text-slate-400">
                            <span title={jobId}>
                              job_id: {formatShortId(jobId)}
                            </span>
                          </p>
                        </div>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="px-4 py-4 text-slate-600">
                      <div className="space-y-1">
                        <p
                          className="text-sm font-medium text-slate-700"
                          title={audit.entity_type}
                        >
                          <span className="block max-w-[140px] truncate">
                            {audit.entity_type}
                          </span>
                        </p>
                        <p
                          className="text-xs text-slate-400"
                          title={audit.entity_id ?? "-"}
                        >
                          <span className="block max-w-[160px] truncate">
                            {audit.entity_id ? formatShortId(audit.entity_id) : "-"}
                          </span>
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-500">
                      <span className="block max-w-[240px] break-words">
                        {audit.meta_json ? JSON.stringify(audit.meta_json) : "-"}
                      </span>
                    </td>
                  </tr>
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

export default AuditPage;
