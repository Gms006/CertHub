import { useEffect, useState } from "react";

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
  is_allowed: boolean;
  auto_approve?: boolean;
  assigned_user?: {
    ad_username: string;
    email?: string | null;
    nome?: string | null;
  } | null;
};

const DevicesPage = () => {
  const { apiFetch, user } = useAuth();
  const { toast, notify } = useToast();
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<DeviceRead | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

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
          auto_approve: Boolean((device as { auto_approve?: boolean }).auto_approve),
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

  const handleAutoApproveToggle = async (deviceId: string, nextValue: boolean) => {
    try {
      const response = await apiFetch(`/admin/devices/${deviceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ auto_approve: nextValue }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Não foi possível atualizar auto approve.", "error");
        return;
      }
      notify(nextValue ? "Auto approve ativado." : "Auto approve desativado.");
      loadDevices();
      setModalOpen(false);
    } catch {
      notify("Erro ao atualizar auto approve.", "error");
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
              className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p
                    className="truncate text-sm font-semibold text-slate-900"
                    title={device.hostname}
                  >
                    {device.hostname}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {formatUserLabel(device)}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold ${
                    device.is_allowed
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-rose-50 text-rose-700"
                  }`}
                >
                  {device.is_allowed ? "Autorizado" : "Bloqueado"}
                </span>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl bg-slate-50 p-3 text-xs text-slate-500">
                  <p className="font-semibold text-slate-500">Agent</p>
                  <p className="mt-1 text-sm font-semibold text-slate-700">
                    {device.agent_version ?? "-"}
                  </p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-3 text-xs text-slate-500">
                  <p className="font-semibold text-slate-500">Último sinal</p>
                  <p className="mt-1 text-sm font-semibold text-slate-700">
                    {formatRelativeTime(device.last_seen_at)}
                  </p>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  className="h-10 flex-1 rounded-2xl border border-slate-200 text-sm text-slate-600"
                  onClick={() => {
                    setSelectedDevice(device);
                    setModalOpen(true);
                  }}
                >
                  Gerenciar
                </button>
                <button
                  className="h-10 flex-1 rounded-2xl bg-[#0e2659] text-sm font-semibold text-white"
                  onClick={() => handleToggle(device.id, !device.is_allowed)}
                >
                  {device.is_allowed ? "Bloquear" : "Autorizar"}
                </button>
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
          <div className="space-y-3">
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs text-slate-400">Hostname</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {selectedDevice.hostname}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Usuário: {formatUserLabel(selectedDevice)}
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Agent</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedDevice.agent_version ?? "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Último contato</p>
                <p className="mt-2 text-sm text-slate-700">
                  {formatDate(selectedDevice.last_seen_at)}
                </p>
              </div>
            </div>
            {isDev ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      Auto approve
                    </p>
                    <p className="text-xs text-slate-500">
                      Aprovar automaticamente instalações para este device.
                    </p>
                  </div>
                  <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      className="h-4 w-4 rounded border-slate-300"
                      checked={Boolean(selectedDevice.auto_approve)}
                      onChange={(event) =>
                        handleAutoApproveToggle(
                          selectedDevice.id,
                          event.target.checked,
                        )
                      }
                    />
                    {selectedDevice.auto_approve ? "Ativo" : "Inativo"}
                  </label>
                </div>
              </div>
            ) : (
              <div className="rounded-2xl border border-slate-200 bg-white p-4">
                <p className="text-sm font-semibold text-slate-900">Auto approve</p>
                <p className="mt-1 text-xs text-slate-500">
                  {selectedDevice.auto_approve ? "Ativo" : "Inativo"}
                </p>
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
