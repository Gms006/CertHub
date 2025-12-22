import { NavLink } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const SectionTabs = () => {
  const { user } = useAuth();
  const role = user?.role_global ?? "VIEW";

  const tabs = [
    { label: "Certificados", to: "/certificados", allow: true },
    { label: "Jobs", to: "/jobs", allow: true },
    { label: "Dispositivos", to: "/dispositivos", allow: role !== "VIEW" },
    { label: "Auditoria", to: "/auditoria", allow: role !== "VIEW" },
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
              `rounded-full px-4 py-2 ${
                isActive ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"
              }`
            }
          >
            {tab.label}
          </NavLink>
        ))}
    </div>
  );
};

export default SectionTabs;
