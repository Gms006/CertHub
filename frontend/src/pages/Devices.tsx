import { useEffect, useState } from "react";
import {
  Monitor,
  Settings,
  ShieldCheck,
  ShieldX,
  UserCircle2,
} from "lucide-react";

import Modal from "../components/Modal";
import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { formatDate, formatRelativeTime } from "../lib/formatters";

type DeviceRead = {
  id: string;
  hostname: string;
  domain?: string | null;
  agent_version?: string | null;
  last_seen_at?: string | null;
  last_heartbeat_at?: string | null;
  last_job_at?: string | null;
  auto_approve?: boolean;
  allow_keep_until?: boolean;
  allow_exempt?: boolean;
  is_allowed: boolean;
  assigned_user?: {
    id: string;
    ad_username: string;
    email?: string | null;
    nome?: string | null;
    auto_approve_install_jobs?: boolean;
  } | null;
};

const DevicesPage = () => {
  const { apiFetch, user } = useAuth();
  const { toast, notify } = useToast();
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<DeviceRead | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [retentionUpdating, setRetentionUpdating] = useState<Record<string, boolean>>(
    {},
  );

  const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";
  const isDev = user?.role_global === "DEV";

  const loadDevices = async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/admin/devices");
      if (!response.ok) {
        notify("Não foi possível carregar devices.", "error");
        return;
      }
      const data = (await response.json()) as DeviceRead[];
      setDevices(
        data.map((device) => ({
          ...device,
          auto_approve: device.auto_approve ?? false,
          allow_keep_until: device.allow_keep_until ?? true,
          allow_exempt: device.allow_exempt ?? true,
          assigned_user: device.assigned_user
            ? {
                ...device.assigned_user,
                auto_approve_install_jobs:
                  device.assigned_user.auto_approve_install_jobs ?? false,
              }
            : null,
        })),
      );
    } catch {
      notify("Erro ao carregar devices.", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadDevices();
    }
  }, [isAdmin]);

  useEffect(() => {
    if (!modalOpen || !selectedDevice) return;
    const fresh = devices.find((device) => device.id === selectedDevice.id);
    if (fresh) {
      setSelectedDevice(fresh);
    }
  }, [devices, modalOpen, selectedDevice?.id]);

  const formatUserLabel = (device: DeviceRead | null) => {
    if (!device?.assigned_user) {
      return "Não vinculado";
    }
    return (
      device.assigned_user.nome ||
      device.assigned_user.ad_username ||
      device.assigned_user.email ||
      "-"
    );
  };

  const formatDomainUser = (device: DeviceRead) => {
    const userLabel = formatUserLabel(device);
    if (device.domain && userLabel !== "Não vinculado") {
      return `${device.domain}\\${userLabel}`;
    }
    if (device.domain) {
      return device.domain;
    }
    return userLabel;
  };

  const handleToggle = async (deviceId: string, nextAllowed: boolean) => {
    try {
      const response = await apiFetch(`/admin/devices/${deviceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_allowed: nextAllowed }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível atualizar o device.", "error");
        return;
      }
      notify(nextAllowed ? "Device autorizado." : "Device bloqueado.");
      loadDevices();
      setModalOpen(false);
    } catch {
      notify("Erro ao atualizar device.", "error");
    }
  };

  const handleAutoApproveToggle = async (userId: string, nextValue: boolean) => {
    try {
      const response = await apiFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_approve_install_jobs: nextValue }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível atualizar auto approve.", "error");
        return;
      }
      notify(nextValue ? "Auto approve ativado." : "Auto approve desativado.");
      setDevices((prev) =>
        prev.map((device) =>
          device.assigned_user?.id === userId
            ? {
                ...device,
                assigned_user: device.assigned_user
                  ? {
                      ...device.assigned_user,
                      auto_approve_install_jobs: nextValue,
                    }
                  : null,
              }
            : device,
        ),
      );
      setSelectedDevice((prev) =>
        prev && prev.assigned_user?.id === userId
          ? {
              ...prev,
              assigned_user: prev.assigned_user
                ? { ...prev.assigned_user, auto_approve_install_jobs: nextValue }
                : null,
            }
          : prev,
      );
      loadDevices();
    } catch {
      notify("Erro ao atualizar auto approve.", "error");
    }
  };

  const handleRetentionToggle = async (
    deviceId: string,
    field: "allow_keep_until" | "allow_exempt",
    nextValue: boolean,
  ) => {
    if (!isDev) {
      return;
    }
    const updateKey = `${deviceId}:${field}`;
    setRetentionUpdating((prev) => ({ ...prev, [updateKey]: true }));
    try {
      const response = await apiFetch(`/admin/devices/${deviceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: nextValue }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível atualizar retenção.", "error");
        return;
      }
      notify(
        field === "allow_keep_until"
          ? nextValue
            ? "Keep Until permitido."
            : "Keep Until bloqueado."
          : nextValue
            ? "Exempt permitido."
            : "Exempt bloqueado.",
      );
      setDevices((prev) =>
        prev.map((device) =>
          device.id === deviceId
            ? {
                ...device,
                [field]: nextValue,
              }
            : device,
        ),
      );
      setSelectedDevice((prev) =>
        prev && prev.id === deviceId
          ? {
              ...prev,
              [field]: nextValue,
            }
          : prev,
      );
      loadDevices();
    } catch {
      notify("Erro ao atualizar retenção.", "error");
    } finally {
      setRetentionUpdating((prev) => {
        const next = { ...prev };
        delete next[updateKey];
        return next;
      });
    }
  };

  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            Dispositivos e Usuários
          </h1>
          <p className="text-sm text-slate-500">
            Acesso restrito para administradores e desenvolvedores.
          </p>
        </div>
        <SectionTabs />
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Você não tem permissão para acessar esta aba.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">
          Dispositivos e Usuários
        </h1>
        <p className="text-sm text-slate-500">
          Gerencie autorizações do Agent e acompanhe status dos hosts.
        </p>
      </div>

      <SectionTabs />

      {loading ? (
        <div className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70" />
      ) : devices.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Nenhum device encontrado.
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {devices.map((device) => (
            <div
              key={device.id}
              className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
                  <Monitor className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p
                        className="truncate text-sm font-semibold text-slate-900"
                        title={device.hostname}
                      >
                        {device.hostname}
                      </p>
                      <p className="mt-1 text-xs text-slate-400">
                        {formatDomainUser(device)}
                      </p>
                    </div>
                    <span
                      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                        device.is_allowed
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-rose-50 text-rose-700"
                      }`}
                    >
                      {device.is_allowed ? "Autorizado" : "Bloqueado"}
                    </span>
                  </div>
                  <div className="space-y-1 text-xs text-slate-500">
                    <div className="flex items-center justify-between">
                      <span>Agent</span>
                      <span className="font-semibold text-slate-700">
                        {device.agent_version ?? "-"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Último sinal</span>
                      <span className="font-semibold text-slate-700">
                        {formatRelativeTime(device.last_job_at)}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Retention</span>
                      <span className="flex flex-wrap justify-end gap-1 text-[10px] font-semibold">
                        {device.allow_keep_until ? (
                          <span className="rounded-full bg-sky-50 px-2 py-0.5 text-sky-700">
                            Keep Until
                          </span>
                        ) : null}
                        {device.allow_exempt ? (
                          <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">
                            Exempt
                          </span>
                        ) : null}
                        {isDev &&
                        !device.allow_keep_until &&
                        !device.allow_exempt ? (
                          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-500">
                            Disabled
                          </span>
                        ) : null}
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-600"
                      onClick={() => {
                        setSelectedDevice(device);
                        setModalOpen(true);
                      }}
                    >
                      <Settings className="h-3.5 w-3.5" />
                      Gerenciar
                    </button>
                    <button
                      className="inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-2xl bg-[#0e2659] px-3 text-xs font-semibold text-white"
                      onClick={() => handleToggle(device.id, !device.is_allowed)}
                    >
                      {device.is_allowed ? (
                        <>
                          <ShieldX className="h-3.5 w-3.5" />
                          Bloquear
                        </>
                      ) : (
                        <>
                          <ShieldCheck className="h-3.5 w-3.5" />
                          Autorizar
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        title="Gerenciar dispositivo"
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        footer={
          selectedDevice ? (
            <>
              <button
                className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
                onClick={() => setModalOpen(false)}
              >
                Fechar
              </button>
              <button
                className="h-10 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white"
                onClick={() =>
                  handleToggle(selectedDevice.id, !selectedDevice.is_allowed)
                }
              >
                {selectedDevice.is_allowed ? "Bloquear" : "Autorizar"}
              </button>
            </>
          ) : null
        }
      >
        {selectedDevice && (
          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white text-slate-500">
                  <Monitor className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-xs text-slate-400">Hostname</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {selectedDevice.hostname}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    {formatDomainUser(selectedDevice)}
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-2 text-xs text-slate-500 md:grid-cols-2">
                <div className="flex items-center justify-between">
                  <span>Agent</span>
                  <span className="font-semibold text-slate-700">
                    {selectedDevice.agent_version ?? "-"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Último contato</span>
                  <span className="font-semibold text-slate-700">
                    {formatDate(selectedDevice.last_seen_at)}
                  </span>
                </div>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <UserCircle2 className="h-4 w-4" />
                Usuário vinculado
              </div>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {formatUserLabel(selectedDevice)}
              </p>
            </div>
            {isDev ? (
              <>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        Auto approve
                      </p>
                      <p className="text-xs text-slate-500">
                        Aprovar automaticamente instalações para o usuário vinculado.
                      </p>
                    </div>
                    <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={Boolean(
                          selectedDevice.assigned_user?.auto_approve_install_jobs,
                        )}
                        disabled={!selectedDevice.assigned_user}
                        onChange={(event) =>
                          selectedDevice.assigned_user
                            ? handleAutoApproveToggle(
                                selectedDevice.assigned_user.id,
                                event.target.checked,
                              )
                            : undefined
                        }
                      />
                      {selectedDevice.assigned_user?.auto_approve_install_jobs
                        ? "Ativo"
                        : "Inativo"}
                    </label>
                  </div>
                  {!selectedDevice.assigned_user ? (
                    <p className="mt-2 text-xs text-slate-400">
                      Vincule um usuário para habilitar o auto approve.
                    </p>
                  ) : null}
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        Permitir Keep Until
                      </p>
                      <p className="text-xs text-slate-500">
                        Permite este dispositivo configurar retenção por tempo (Keep
                        Until).
                      </p>
                    </div>
                    <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={Boolean(selectedDevice.allow_keep_until)}
                        disabled={
                          retentionUpdating[`${selectedDevice.id}:allow_keep_until`]
                        }
                        onChange={(event) =>
                          handleRetentionToggle(
                            selectedDevice.id,
                            "allow_keep_until",
                            event.target.checked,
                          )
                        }
                      />
                      {selectedDevice.allow_keep_until ? "Ativo" : "Inativo"}
                    </label>
                  </div>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        Permitir Exempt
                      </p>
                      <p className="text-xs text-slate-500">
                        Permite este dispositivo marcar certificado como isento de
                        limpeza (Exempt).
                      </p>
                    </div>
                    <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-600">
                      <input
                        type="checkbox"
                        className="h-4 w-4 rounded border-slate-300"
                        checked={Boolean(selectedDevice.allow_exempt)}
                        disabled={retentionUpdating[`${selectedDevice.id}:allow_exempt`]}
                        onChange={(event) =>
                          handleRetentionToggle(
                            selectedDevice.id,
                            "allow_exempt",
                            event.target.checked,
                          )
                        }
                      />
                      {selectedDevice.allow_exempt ? "Ativo" : "Inativo"}
                    </label>
                  </div>
                </div>
              </>
            ) : (
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Retention</p>
                <p className="text-xs text-slate-500">
                  Status das permissões de retenção do dispositivo.
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-[11px] font-semibold text-slate-600">
                  {selectedDevice.allow_keep_until ? (
                    <span className="rounded-full bg-sky-50 px-2.5 py-1 text-sky-700">
                      Keep Until ativo
                    </span>
                  ) : null}
                  {selectedDevice.allow_exempt ? (
                    <span className="rounded-full bg-amber-50 px-2.5 py-1 text-amber-700">
                      Exempt ativo
                    </span>
                  ) : null}
                  {!selectedDevice.allow_keep_until && !selectedDevice.allow_exempt ? (
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-500">
                      Sem permissões
                    </span>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
};

export default DevicesPage;
