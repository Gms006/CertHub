import { useEffect, useMemo, useState } from "react";

import Modal from "../components/Modal";
import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { formatDate } from "../lib/formatters";

type DeviceRead = {
  id: string;
  hostname: string;
  domain?: string | null;
  agent_version?: string | null;
  last_seen_at?: string | null;
  is_allowed: boolean;
};

type UserDeviceReadWithUser = {
  device_id: string;
  user: {
    ad_username: string;
    email?: string | null;
    nome?: string | null;
  };
};

const DevicesPage = () => {
  const { apiFetch, user } = useAuth();
  const { toast, notify } = useToast();
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [links, setLinks] = useState<UserDeviceReadWithUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDevice, setSelectedDevice] = useState<DeviceRead | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";

  const loadDevices = async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/admin/devices");
      if (!response.ok) {
        notify("Não foi possível carregar devices.", "error");
        return;
      }
      const data = (await response.json()) as DeviceRead[];
      setDevices(data);
    } catch {
      notify("Erro ao carregar devices.", "error");
    } finally {
      setLoading(false);
    }
  };

  const loadLinks = async () => {
    try {
      const response = await apiFetch("/admin/user-devices");
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as UserDeviceReadWithUser[];
      setLinks(data);
    } catch {
      // silencioso
    }
  };

  useEffect(() => {
    if (isAdmin) {
      loadDevices();
      loadLinks();
    }
  }, [isAdmin]);

  const deviceUserMap = useMemo(() => {
    const map = new Map<string, string>();
    links.forEach((link) => {
      const label = link.user.nome || link.user.ad_username || link.user.email || "-";
      map.set(link.device_id, label);
    });
    return map;
  }, [links]);

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

  if (!isAdmin) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Dispositivos</h1>
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
        <h1 className="text-2xl font-semibold text-slate-900">Dispositivos</h1>
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
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    {device.hostname}
                  </p>
                  <p className="text-xs text-slate-400">
                    Usuário: {deviceUserMap.get(device.id) ?? "Não vinculado"}
                  </p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs font-semibold ${
                    device.is_allowed
                      ? "bg-emerald-50 text-emerald-700"
                      : "bg-rose-50 text-rose-700"
                  }`}
                >
                  {device.is_allowed ? "Autorizado" : "Bloqueado"}
                </span>
              </div>
              <div className="mt-4 grid gap-3 text-xs text-slate-500">
                <div className="flex items-center justify-between">
                  <span>Agent</span>
                  <span className="text-slate-700">{device.agent_version ?? "-"}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Último contato</span>
                  <span className="text-slate-700">{formatDate(device.last_seen_at)}</span>
                </div>
              </div>
              <button
                className="mt-4 h-10 w-full rounded-2xl border border-slate-200 text-sm text-slate-600"
                onClick={() => {
                  setSelectedDevice(device);
                  setModalOpen(true);
                }}
              >
                Gerenciar
              </button>
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
                Usuário: {deviceUserMap.get(selectedDevice.id) ?? "Não vinculado"}
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
          </div>
        )}
      </Modal>

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
};

export default DevicesPage;
