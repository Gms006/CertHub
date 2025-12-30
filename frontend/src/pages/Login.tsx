import { FormEvent, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { API_BASE } from "../lib/apiClient";
import { formatRelativeTime } from "../lib/formatters";

type DeviceInfo = {
  hostname: string;
  domain?: string | null;
  agent_version?: string | null;
  last_seen_at?: string | null;
};

const getCookieValue = (name: string) => {
  if (typeof document === "undefined") return null;
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
};

const Login = () => {
  const { login, loading, message, accessToken } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const result = await login(email, password);
    if (result) {
      navigate("/certificados", { replace: true });
    }
  };

  useEffect(() => {
    if (accessToken) {
      navigate("/certificados", { replace: true });
    }
  }, [accessToken, navigate]);

  useEffect(() => {
    const loadDeviceInfo = async () => {
      const deviceId =
        localStorage.getItem("certhub_device_id") ||
        sessionStorage.getItem("certhub_device_id") ||
        getCookieValue("certhub_device_id");
      const deviceToken =
        localStorage.getItem("certhub_device_token") ||
        sessionStorage.getItem("certhub_device_token") ||
        getCookieValue("certhub_device_token");
      if (!deviceId || !deviceToken) {
        return;
      }
      try {
        const authResponse = await fetch(`${API_BASE}/agent/auth`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_id: deviceId, device_token: deviceToken }),
        });
        if (!authResponse.ok) {
          return;
        }
        const authData = (await authResponse.json()) as { access_token: string };
        const meResponse = await fetch(`${API_BASE}/agent/me`, {
          headers: { Authorization: `Bearer ${authData.access_token}` },
        });
        if (!meResponse.ok) {
          return;
        }
        const device = (await meResponse.json()) as DeviceInfo;
        setDeviceInfo(device);
      } catch {
        // silencioso
      }
    };

    loadDeviceInfo();
  }, []);

  const deviceLabel = useMemo(() => {
    if (!deviceInfo) return "Device não identificado";
    if (deviceInfo.domain) {
      return `${deviceInfo.domain}\\${deviceInfo.hostname}`;
    }
    return deviceInfo.hostname;
  }, [deviceInfo]);

  const deviceMeta = useMemo(() => {
    if (!deviceInfo) return "Agent indisponível";
    const version = deviceInfo.agent_version ?? "-";
    const lastSeen = formatRelativeTime(deviceInfo.last_seen_at);
    return `Agent ${version} • ${lastSeen}`;
  }, [deviceInfo]);

  return (
    <div className="relative min-h-screen bg-slate-100">
      <div className="pointer-events-none absolute left-[-120px] top-24 h-64 w-64 rounded-full border border-[#22489c]/25" />
      <div className="pointer-events-none absolute left-[-60px] top-36 h-44 w-44 rounded-full border border-[#22489c]/20" />
      <div className="pointer-events-none absolute left-[-20px] top-48 h-28 w-28 rounded-full border border-[#22489c]/15" />
      <div className="pointer-events-none absolute right-[-80px] top-[-40px] h-56 w-56 rounded-full bg-[#22489c]/10 blur-3xl" />

      <div className="mx-auto flex min-h-screen max-w-7xl items-center px-4 py-10">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-soft lg:max-w-[1100px]"
        >
          <div className="grid grid-cols-1 lg:grid-cols-2">
            <div className="flex flex-col gap-6 px-8 py-10 lg:px-10">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#0e2659] text-white">
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2 5 5v6c0 5.25 3.44 10 7 11 3.56-1 7-5.75 7-11V5l-7-3Z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    Neto Contabilidade
                  </p>
                  <p className="text-xs text-slate-500">Portal de Certificados</p>
                </div>
              </div>
              <div>
                <h2 className="text-xl font-semibold text-slate-900">Entrar</h2>
                <p className="mt-2 text-sm text-slate-500">
                  Acesse com seu e-mail corporativo e senha.
                </p>
              </div>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <label className="block text-xs font-semibold text-slate-500">
                  E-mail
                  <div className="relative mt-2">
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
                        <path d="M4 4h16v16H4z" />
                        <path d="m4 6 8 6 8-6" />
                      </svg>
                    </span>
                    <input
                      className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 text-sm text-slate-700 placeholder:text-slate-400"
                      type="email"
                      placeholder="maria.clara@netocontabilidade.com.br"
                      value={email}
                      onChange={(event) => setEmail(event.target.value)}
                      required
                    />
                  </div>
                </label>
                <label className="block text-xs font-semibold text-slate-500">
                  Senha
                  <div className="relative mt-2">
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
                        <rect x="3" y="11" width="18" height="11" rx="2" />
                        <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                      </svg>
                    </span>
                    <input
                      className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 pr-11 text-sm text-slate-700 placeholder:text-slate-400"
                      type={showPassword ? "text" : "password"}
                      placeholder="Senha segura"
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((prev) => !prev)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600"
                    >
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
                        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12Z" />
                        <circle cx="12" cy="12" r="3" />
                      </svg>
                    </button>
                  </div>
                  <span className="mt-2 block text-[11px] text-slate-400">
                    Somente contas do domínio @netocontabilidade.com.br.
                  </span>
                </label>
                <button
                  className="h-11 w-full rounded-2xl bg-[#0e2659] text-sm font-semibold text-white transition hover:bg-[#0e2659]/90"
                  type="submit"
                  disabled={loading}
                >
                  {loading ? "Entrando..." : "Acessar"}
                </button>
              </form>
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-500">
                <div className="flex items-center justify-between gap-3 text-[11px] text-slate-500">
                  <span>Instalação: CurrentUser</span>
                  <span>Remoção: 18:00</span>
                  <span>Auditoria: habilitada</span>
                </div>
                <p className="mt-3 text-[11px]">
                  O portal cria o job. O Agent instala. Tudo fica registrado por
                  usuário e device.
                </p>
              </div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>© 2025 Neto Contabilidade</span>
                <span>Versão: 0.1.0</span>
              </div>
            </div>

            <div className="relative overflow-hidden bg-slate-950 px-8 py-10 text-white">
              <div className="absolute right-10 top-6 rounded-full bg-white/10 px-3 py-1 text-xs text-white/80">
                Acesso controlado + auditoria
              </div>
              <div className="absolute left-6 top-16 h-20 w-20 rounded-full border border-white/10" />
              <div className="absolute left-24 top-28 h-16 w-16 rounded-full border border-white/10" />
              <div className="absolute bottom-[-90px] right-[-80px] h-56 w-56 rounded-full bg-gradient-to-br from-[#22489c] to-[#0e2659] opacity-95" />
              <div className="dot-grid pointer-events-none absolute inset-0 opacity-30" />

              <div className="relative space-y-8">
                <div>
                  <p className="text-xs text-white/55">Portal corporativo</p>
                  <h2 className="mt-3 text-3xl font-semibold leading-tight">
                    O cofre{" "}
                    <span className="text-[#6ea3ff]">de certificados</span> do
                    escritório
                  </h2>
                  <p className="mt-4 text-sm text-white/70">
                    Instalação via Agent no Windows, sem expor arquivos/senhas ao
                    time — e com histórico por usuário e máquina.
                  </p>
                </div>
                <div className="rounded-3xl bg-white p-6 text-slate-900 shadow-soft">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-full bg-slate-100" />
                    <div>
                      <p className="text-sm font-semibold">Maria Clara</p>
                      <p className="text-xs text-slate-500">
                        Neto Contabilidade
                      </p>
                    </div>
                  </div>
                  <p className="mt-4 text-sm text-slate-600">
                    A facilidade de instalar certificados sem abrir pastas nem
                    procurar senhas é o que mais muda o jogo. E a auditoria por
                    usuário/device traz controle de verdade.
                  </p>
                  <div className="mt-4 flex gap-2">
                    {["Jobs", "Devices", "Auditoria"].map((badge) => (
                      <span
                        key={badge}
                        className="rounded-full bg-slate-900 px-3 py-1 text-[11px] font-semibold text-white"
                      >
                        {badge}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-2xl bg-white/10 p-4 text-xs text-white/70">
                    <p className="text-white">Device</p>
                    <p className="mt-2 text-sm text-white">
                      {deviceLabel}
                    </p>
                    <p className="mt-1 text-[11px] text-white/60">
                      {deviceMeta}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-white/10 p-4 text-xs text-white/70">
                    <p className="text-white">Segurança</p>
                    <p className="mt-2 text-sm text-white">
                      Sem PFX no browser
                    </p>
                    <p className="mt-1 text-[11px] text-white/60">
                      Somente o Agent manuseia o certificado.
                    </p>
                  </div>
                </div>
                <p className="text-xs text-white/55">
                  Se não conseguir acessar, solicite suporte ao TI.
                </p>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {message && (
        <div className="fixed bottom-5 right-5 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700 shadow-soft">
          {message}
        </div>
      )}
    </div>
  );
};

export default Login;
