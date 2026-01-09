import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { Bell } from "lucide-react";

import { useAuth } from "../hooks/useAuth";

type InstallJobRead = {
  status: string;
};

const SectionTabs = () => {
  const { user, apiFetch } = useAuth();
  const role = user?.role_global ?? "VIEW";
  const [requestedCount, setRequestedCount] = useState(0);
  const isAdmin = role === "ADMIN" || role === "DEV";

  useEffect(() => {
    if (!isAdmin) {
      setRequestedCount(0);
      return;
    }
    let mounted = true;
    const loadRequestedCount = async () => {
      try {
        const response = await apiFetch("/install-jobs");
        if (!response.ok) {
          if (mounted) {
            setRequestedCount(0);
          }
          return;
        }
        const data = (await response.json()) as InstallJobRead[];
        if (mounted) {
          setRequestedCount(
            data.filter((job) => job.status === "REQUESTED").length,
          );
        }
      } catch {
        if (mounted) {
          setRequestedCount(0);
        }
      }
    };
    loadRequestedCount();
    const interval = window.setInterval(loadRequestedCount, 20000);
    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, [apiFetch, isAdmin]);

  const tabs = [
    { label: "Certificados", to: "/certificados", allow: true },
    { label: "Solicitações", to: "/jobs", allow: true },
    { label: "Instalados", to: "/instalados", allow: true },
    { label: "Dispositivos e Usuários", to: "/dispositivos", allow: role !== "VIEW" },
    { label: "Auditoria", to: "/auditoria", allow: role === "DEV" },
  ];

  return (
    <div className="flex flex-wrap gap-3 text-sm font-medium text-slate-500">
      {tabs
        .filter((tab) => tab.allow)
        .map((tab) => (
          <NavLink
            key={tab.label}
            to={tab.to}
            className={({ isActive }) =>
              `inline-flex items-center gap-2 rounded-full px-4 py-2 ${
                isActive ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
              }`
            }
          >
            <span>{tab.label}</span>
            {tab.label === "Solicitações" && requestedCount > 0 ? (
              <span
                className="relative inline-flex h-5 w-5 items-center justify-center rounded-full bg-amber-100 text-amber-700"
                aria-label={`${requestedCount} job(s) aguardando aprovação`}
                title={`${requestedCount} job(s) aguardando aprovação`}
              >
                <Bell className="h-3 w-3" />
                <span className="absolute -right-2 -top-2 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold text-white">
                  {requestedCount}
                </span>
              </span>
            ) : null}
          </NavLink>
        ))}
    </div>
  );
};

export default SectionTabs;
