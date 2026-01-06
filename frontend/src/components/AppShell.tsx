import { useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { Search, SlidersHorizontal } from "lucide-react";

import Modal from "./Modal";
import { useAuth } from "../hooks/useAuth";
import { usePreferences } from "../hooks/usePreferences";

const AppShell = () => {
  const { user, logout, apiFetch } = useAuth();
  const { preferences, updatePreferences } = usePreferences();
  const displayName =
    user?.nome || user?.ad_username || user?.email || "Usuário";
  const isDev = user?.role_global === "DEV";
  const [preferencesOpen, setPreferencesOpen] = useState(false);
  const [deviceOptions, setDeviceOptions] = useState<
    { id: string; hostname: string; assigned_user?: { ad_username?: string } | null }[]
  >([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const hasDefaultDevice = deviceOptions.some(
    (device) => device.id === preferences.defaultDeviceId,
  );

  useEffect(() => {
    if (!preferencesOpen) return;
    let mounted = true;
    const loadDevices = async () => {
      setDevicesLoading(true);
      try {
        const response = await apiFetch("/devices/mine");
        if (!response.ok) {
          if (mounted) {
            setDeviceOptions([]);
          }
          return;
        }
        const data = (await response.json()) as {
          id: string;
          hostname: string;
          assigned_user?: { ad_username?: string } | null;
        }[];
        if (mounted) {
          setDeviceOptions(data);
        }
      } catch {
        if (mounted) {
          setDeviceOptions([]);
        }
      } finally {
        if (mounted) {
          setDevicesLoading(false);
        }
      }
    };
    loadDevices();
    return () => {
      mounted = false;
    };
  }, [apiFetch, preferencesOpen]);

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="flex w-full items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#0e2659] text-white">
              <span className="text-sm font-semibold">N</span>
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900">
                Neto Contabilidade
              </p>
              <p className="text-xs text-slate-500">Portal de Certificados</p>
            </div>
          </div>
          <div className="hidden w-full max-w-xl items-center gap-3 md:flex">
            <div className="relative flex-1">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                <Search className="h-4 w-4" />
              </span>
              <input
                className="h-10 w-full rounded-2xl border border-slate-200 bg-white pl-9 text-sm text-slate-600 placeholder:text-slate-400"
                placeholder="Buscar por empresa, CNPJ/CPF, titular..."
              />
            </div>
            <button
              className="flex h-10 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600"
              onClick={() => setPreferencesOpen(true)}
            >
              <SlidersHorizontal className="h-4 w-4" />
              Preferências
            </button>
          </div>
          <div className="flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-xs font-semibold text-white">
            <span>{displayName}</span>
            <span className="text-white/40">•</span>
            <button
              type="button"
              onClick={logout}
              className="text-xs font-semibold text-white/80 transition hover:text-white"
            >
              Sair
            </button>
          </div>
        </div>
      </header>
      <div className="grid w-full gap-6 px-4 py-6 md:grid-cols-[260px_1fr]">
        <aside className="space-y-4 rounded-3xl bg-gradient-to-br from-[#0e2659] to-[#22489c] p-4 text-white shadow-soft">
          <div className="rounded-2xl bg-white/10 p-4">
            <p className="text-xs uppercase tracking-wide text-white/60">
              Área Interna
            </p>
            <p className="mt-2 text-sm font-semibold">Acesso controlado + Auditoria</p>
            <span className="mt-3 inline-flex rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-semibold">
              Piloto
            </span>
          </div>
          <div className="space-y-3">
            {[
              {
                title: "Limpeza automática",
                body: "Todos temporários removidos às 18:00",
                foot: "Somente certificados instalados pelo Agent",
              },
              {
                title: "Agent",
                body: "Instala no CurrentUser",
                foot: "Sem expor arquivo/senha ao navegador.",
              },
              {
                title: "Auditoria",
                body: "Quem, quando e onde",
                foot: "Jobs, devices e histórico por empresa.",
              },
            ].map((item) => (
              <div key={item.title} className="rounded-2xl bg-white/10 p-4">
                <p className="text-xs font-semibold text-white/70">{item.title}</p>
                <p className="mt-2 text-sm font-semibold">{item.body}</p>
                <p className="mt-2 text-xs text-white/60">{item.foot}</p>
              </div>
            ))}
          </div>
          <div className="rounded-2xl bg-white/10 p-4 text-xs text-white/70">
            <p>
              AD: NETOCMS • CurrentUser store
            </p>
          </div>
        </aside>
        <main>
          <Outlet />
        </main>
      </div>

      <Modal
        title="Preferências"
        open={preferencesOpen}
        onClose={() => setPreferencesOpen(false)}
        footer={
          <button
            className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
            onClick={() => setPreferencesOpen(false)}
          >
            Fechar
          </button>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <label className="flex flex-col gap-2 text-xs font-semibold text-slate-500">
            Tamanho da página
            <select
              className="h-10 rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-600"
              value={preferences.pageSize}
              onChange={(event) =>
                updatePreferences({ pageSize: Number(event.target.value) })
              }
            >
              {[6, 9, 12, 18].map((size) => (
                <option key={size} value={size}>
                  {size} itens
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-2 text-xs font-semibold text-slate-500">
            Ordenação padrão
            <select
              className="h-10 rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-600"
              value={preferences.defaultOrder}
              onChange={(event) =>
                updatePreferences({
                  defaultOrder: event.target.value as "validade" | "empresa",
                })
              }
            >
              <option value="validade">Validade</option>
              <option value="empresa">Empresa</option>
            </select>
          </label>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <label className="flex items-center justify-between rounded-2xl border border-slate-200 p-3 text-xs font-semibold text-slate-600">
            Auto-refresh Jobs
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={preferences.autoRefreshJobs}
              onChange={(event) =>
                updatePreferences({ autoRefreshJobs: event.target.checked })
              }
            />
          </label>
          <label className="flex items-center justify-between rounded-2xl border border-slate-200 p-3 text-xs font-semibold text-slate-600">
            Auto-refresh Auditoria
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={preferences.autoRefreshAudit}
              onChange={(event) =>
                updatePreferences({ autoRefreshAudit: event.target.checked })
              }
            />
          </label>
        </div>
        <label className="flex items-center justify-between rounded-2xl border border-slate-200 p-3 text-xs font-semibold text-slate-600">
          Ocultar IDs longos
          <input
            type="checkbox"
            className="h-4 w-4 rounded border-slate-300"
            checked={preferences.hideLongIds}
            onChange={(event) =>
              updatePreferences({ hideLongIds: event.target.checked })
            }
          />
        </label>
        <label className="flex flex-col gap-2 text-xs font-semibold text-slate-500">
          Device padrão (VIEW)
          <select
            className="h-10 rounded-2xl border border-slate-200 bg-white px-3 text-sm text-slate-600"
            value={preferences.defaultDeviceId}
            onChange={(event) =>
              updatePreferences({ defaultDeviceId: event.target.value })
            }
          >
            <option value="">
              {devicesLoading ? "Carregando devices..." : "Selecione um device"}
            </option>
            {!hasDefaultDevice && preferences.defaultDeviceId ? (
              <option value={preferences.defaultDeviceId}>
                Device atual (não listado)
              </option>
            ) : null}
            {deviceOptions.map((device) => (
              <option key={device.id} value={device.id}>
                {device.hostname}
              </option>
            ))}
          </select>
        </label>
        {isDev ? (
          <a
            className="inline-flex h-10 items-center justify-center rounded-2xl border border-slate-200 px-4 text-xs font-semibold text-slate-600 transition hover:bg-slate-50"
            href="/docs"
            target="_blank"
            rel="noreferrer"
          >
            Abrir Swagger
          </a>
        ) : null}
        <p className="text-[11px] text-slate-400">
          Preferências ficam salvas localmente neste navegador.
        </p>
      </Modal>
    </div>
  );
};

export default AppShell;
