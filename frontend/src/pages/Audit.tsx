import { useEffect, useMemo, useState } from "react";

import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { formatDate } from "../lib/formatters";

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

const formatShortId = (value: string) => value.slice(0, 8);

const AuditPage = () => {
  const { apiFetch } = useAuth();
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

  const filteredAudits = useMemo(() => {
    const actionTerm = actionFilter.trim().toLowerCase();
    const actorTerm = actorFilter.trim().toLowerCase();
    return audits.filter((audit) => {
      const actionOk = actionTerm
        ? audit.action.toLowerCase().includes(actionTerm)
        : true;
      const actorOk = actorTerm
        ? (audit.actor_label ?? "").toLowerCase().includes(actorTerm)
        : true;
      return actionOk && actorOk;
    });
  }, [actionFilter, actorFilter, audits]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Auditoria</h1>
        <p className="text-sm text-slate-500">
          Acompanhe ações críticas realizadas no portal e no Agent.
        </p>
      </div>

      <SectionTabs />

      <div className="flex flex-wrap gap-3 rounded-3xl border border-slate-200 bg-white p-4">
        <input
          className="h-10 flex-1 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          placeholder="Filtrar por ação"
          value={actionFilter}
          onChange={(event) => setActionFilter(event.target.value)}
        />
        <input
          className="h-10 flex-1 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          placeholder="Filtrar por ator"
          value={actorFilter}
          onChange={(event) => setActorFilter(event.target.value)}
        />
        <button
          className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
          onClick={loadAudit}
        >
          Atualizar
        </button>
      </div>

      {loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70" />
      ) : filteredAudits.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Nenhum registro de auditoria encontrado.
        </div>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white">
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
            <tbody>
              {filteredAudits.map((audit) => {
                const jobId = getJobId(audit);
                return (
                  <tr key={audit.id} className="border-t border-slate-100">
                    <td className="px-4 py-4 text-slate-500">
                      {formatDate(audit.timestamp)}
                    </td>
                    <td className="px-4 py-4 text-slate-700">
                      {audit.actor_label ?? "-"}
                    </td>
                    <td className="px-4 py-4">
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                        {audit.action}
                      </span>
                    </td>
                    <td className="px-4 py-4 text-slate-600">
                      {jobId ? (
                        <div className="space-y-1">
                          <span className="inline-flex rounded-full bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-700">
                            {formatShortId(jobId)}
                          </span>
                          <p className="text-[11px] text-slate-400">
                            job_id: {jobId}
                          </p>
                        </div>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="px-4 py-4 text-slate-600">
                      <div className="space-y-1">
                        <p className="text-sm font-medium text-slate-700">
                          {audit.entity_type}
                        </p>
                        <p className="text-xs text-slate-400">
                          {audit.entity_id ?? "-"}
                        </p>
                      </div>
                    </td>
                    <td className="px-4 py-4 text-xs text-slate-500">
                      {audit.meta_json ? JSON.stringify(audit.meta_json) : "-"}
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
