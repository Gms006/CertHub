import { Outlet } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const AppShell = () => {
  const { user, logout } = useAuth();
  const displayName =
    user?.nome || user?.ad_username || user?.email || "Usuário";

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
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <circle cx="11" cy="11" r="8" />
                  <path d="m21 21-4.3-4.3" />
                </svg>
              </span>
              <input
                className="h-10 w-full rounded-2xl border border-slate-200 bg-white pl-9 text-sm text-slate-600 placeholder:text-slate-400"
                placeholder="Buscar por empresa, CNPJ/CPF, titular..."
              />
            </div>
            <button className="flex h-10 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 text-sm font-medium text-slate-600">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 5 15.5a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 8.5 5a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09A1.65 1.65 0 0 0 15.5 4.6a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19 8.5c0 .6.23 1.17.64 1.58.4.41.98.64 1.58.64H21a2 2 0 1 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15Z" />
              </svg>
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
    </div>
  );
};

export default AppShell;
