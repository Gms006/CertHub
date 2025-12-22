import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  BadgeCheck,
  FileBadge2,
  Info,
  KeyRound,
  XCircle,
} from "lucide-react";

import Modal from "../components/Modal";
import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { daysUntil, extractDigits, formatCnpjCpf, formatDate } from "../lib/formatters";

type CertificateRead = {
  id: string;
  name: string;
  subject?: string | null;
  issuer?: string | null;
  serial_number?: string | null;
  sha1_fingerprint?: string | null;
  not_after?: string | null;
  not_before?: string | null;
  created_at: string;
};

type DeviceRead = {
  id: string;
  hostname: string;
  domain?: string | null;
  agent_version?: string | null;
  last_seen_at?: string | null;
  is_allowed?: boolean;
};

type InstallJobRead = {
  id: string;
  status: string;
};

type StatusKey = "valid" | "expiring7" | "expiring30" | "expired";

type StatusInfo = {
  key: StatusKey;
  label: string;
  meta: string;
};

const getStatusInfo = (notAfter?: string | null): StatusInfo => {
  const remaining = daysUntil(notAfter);
  if (remaining === null) {
    return { key: "valid", label: "Válido", meta: "Sem expiração" };
  }
  if (remaining <= 0) {
    return {
      key: "expired",
      label: "Vencido",
      meta: `${Math.abs(remaining)} dias atrasado`,
    };
  }
  if (remaining <= 7) {
    return { key: "expiring7", label: "Vence em 7d", meta: `${remaining} dias` };
  }
  if (remaining <= 30) {
    return { key: "expiring30", label: "Vence em 30d", meta: `${remaining} dias` };
  }
  return { key: "valid", label: "Válido", meta: `${remaining} dias` };
};

type CertStatus = "VALIDO" | "VENCE_7D" | "VENCIDO";

type CertCardProps = {
  empresa: string;
  cnpj: string;
  status: CertStatus;
  validadeISO: string;
  diasLabel?: string;
  titular?: string;
  serial?: string;
  sha1?: string;
  footerUser?: string;
  onInstall?: () => void;
  onDetails?: () => void;
};

const mapStatusToCert = (status: StatusKey): CertStatus => {
  if (status === "expired") return "VENCIDO";
  if (status === "expiring7") return "VENCE_7D";
  return "VALIDO";
};

const toISODate = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toISOString().slice(0, 10);
};

const maskCnpj = (value: string) => {
  const digits = (value || "").replace(/\D/g, "").padStart(14, "0").slice(0, 14);
  return digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
};

const statusUI = (status: CertStatus) => {
  if (status === "VENCIDO") {
    return {
      Icon: XCircle,
      iconClass: "text-red-600",
      badgeClass: "bg-red-600 text-white",
      label: "Vencido",
    };
  }
  if (status === "VENCE_7D") {
    return {
      Icon: AlertTriangle,
      iconClass: "text-amber-600",
      badgeClass: "bg-amber-500 text-white",
      label: "Vence em ≤ 7d",
    };
  }
  return {
    Icon: BadgeCheck,
    iconClass: "text-emerald-600",
    badgeClass: "bg-emerald-600 text-white",
    label: "Válido",
  };
};

const CertCard = ({
  empresa,
  cnpj,
  status,
  validadeISO,
  diasLabel,
  titular,
  serial,
  sha1,
  footerUser,
  onInstall,
  onDetails,
}: CertCardProps) => {
  const ui = statusUI(status);
  const StatusIcon = ui.Icon;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 bg-slate-50">
              <FileBadge2 className="h-4 w-4 text-slate-600" />
            </div>

            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-slate-900">
                {empresa}
              </div>
              <div className="mt-0.5 text-xs text-slate-500">
                CNPJ: {maskCnpj(cnpj)}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2">
            <button
              onClick={onInstall}
              className="inline-flex h-9 w-[120px] items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 text-xs font-semibold text-white hover:bg-slate-800"
            >
              <KeyRound className="h-4 w-4" />
              Instalar
            </button>

            <button
              onClick={onDetails}
              className="inline-flex h-9 w-[120px] items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <Info className="h-4 w-4" />
              Detalhes
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <StatusIcon className={`h-4 w-4 ${ui.iconClass}`} />
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${ui.badgeClass}`}
            >
              {ui.label}
            </span>
          </div>

          <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
            Validade: {validadeISO}
          </span>
        </div>

        {diasLabel ? (
          <div className="mt-2">
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">
              {diasLabel}
            </span>
          </div>
        ) : null}

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[11px] font-semibold text-slate-500">Titular</div>
            <div className="mt-1 truncate text-xs font-semibold text-slate-900">
              {titular || "-"}
            </div>
          </div>

          <div className="rounded-xl bg-slate-50 p-3">
            <div className="text-[11px] font-semibold text-slate-500">
              Identificadores
            </div>

            <div className="mt-1 text-[11px] text-slate-600">
              <span className="font-semibold text-slate-700">Serial:</span>{" "}
              <span className="truncate">{serial || "-"}</span>
            </div>
            <div className="mt-1 text-[11px] text-slate-600">
              <span className="font-semibold text-slate-700">SHA1:</span>{" "}
              <span className="truncate">{sha1 || "-"}</span>
            </div>
          </div>
        </div>

        <div className="mt-4 text-[11px] leading-relaxed text-slate-500">
          Instalação via Agent ({footerUser || "CurrentUser"}). Certificados
          temporários serão removidos automaticamente às 18:00.
        </div>
      </div>
    </div>
  );
};

const CertCardsGrid = ({ children }: { children: ReactNode }) => (
  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">{children}</div>
);

const extractTaxId = (value?: string | null) => {
  if (!value) return "-";
  const digits = extractDigits(value);
  if (digits.length === 11 || digits.length === 14) {
    return formatCnpjCpf(digits);
  }
  const match = value.match(/\d{11}|\d{14}/);
  if (match) {
    return formatCnpjCpf(match[0]);
  }
  return "-";
};

const CertificatesPage = () => {
  const { apiFetch, user } = useAuth();
  const { toast, notify } = useToast();
  const [certificates, setCertificates] = useState<CertificateRead[]>([]);
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [jobs, setJobs] = useState<InstallJobRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("Todos");
  const [orderBy, setOrderBy] = useState("validade");
  const [page, setPage] = useState(1);
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [installCertificateId, setInstallCertificateId] = useState<string | null>(null);
  const [selectedCertificate, setSelectedCertificate] = useState<CertificateRead | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const pageSize = 9;

  const loadCertificates = async () => {
    setLoading(true);
    try {
      const response = await apiFetch("/certificados");
      if (!response.ok) {
        notify("Não foi possível carregar certificados.", "error");
        return;
      }
      const data = (await response.json()) as CertificateRead[];
      setCertificates(data);
    } catch {
      notify("Erro ao carregar certificados.", "error");
    } finally {
      setLoading(false);
    }
  };

  const loadDevices = async () => {
    try {
      const response = await apiFetch("/admin/devices");
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as DeviceRead[];
      setDevices(data);
    } catch {
      // silencioso
    }
  };

  const loadJobs = async () => {
    const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";
    const endpoint = isAdmin ? "/install-jobs" : "/install-jobs/mine";
    try {
      const response = await apiFetch(endpoint);
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as InstallJobRead[];
      setJobs(data);
    } catch {
      // silencioso
    }
  };

  useEffect(() => {
    loadCertificates();
    loadDevices();
  }, []);

  useEffect(() => {
    loadJobs();
  }, [user?.role_global]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, orderBy]);

  const filteredCertificates = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = certificates.filter((cert) => {
      const status = getStatusInfo(cert.not_after).key;
      if (statusFilter !== "Todos") {
        const map: Record<string, StatusKey> = {
          "Válido": "valid",
          "Vence em 7d": "expiring7",
          "Vence em 30d": "expiring30",
          "Vencido": "expired",
        };
        if (map[statusFilter] && map[statusFilter] !== status) {
          return false;
        }
      }
      if (!term) return true;
      const taxId = extractDigits(cert.subject ?? cert.name);
      const haystack = [
        cert.name,
        cert.subject,
        cert.serial_number,
        cert.sha1_fingerprint,
        taxId,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });

    const sorted = [...filtered].sort((a, b) => {
      if (orderBy === "empresa") {
        return a.name.localeCompare(b.name);
      }
      const aTime = a.not_after ? new Date(a.not_after).getTime() : Number.MAX_SAFE_INTEGER;
      const bTime = b.not_after ? new Date(b.not_after).getTime() : Number.MAX_SAFE_INTEGER;
      return aTime - bTime;
    });

    return sorted;
  }, [certificates, orderBy, search, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredCertificates.length / pageSize));
  const pagedCertificates = filteredCertificates.slice(
    (page - 1) * pageSize,
    page * pageSize,
  );

  const kpis = useMemo(() => {
    const statusBuckets = certificates.map((cert) => getStatusInfo(cert.not_after).key);
    const expiredCount = statusBuckets.filter((status) => status === "expired").length;
    const expiring7Count = statusBuckets.filter((status) => status === "expiring7").length;
    return [
      { label: "Certificados", value: `${certificates.length}`, meta: "catalogados no DB" },
      { label: "Vencidos", value: `${expiredCount}`, meta: "exigem ação" },
      { label: "Vence em 7d", value: `${expiring7Count}`, meta: "prioridade" },
      { label: "Jobs ativos", value: `${jobs.length}`, meta: "pendente/progresso" },
      { label: "Devices OK", value: `${devices.filter((d) => d.is_allowed).length}`, meta: "autorizados" },
    ];
  }, [certificates, devices, jobs]);

  const handleOpenInstall = (certificateId?: string) => {
    setInstallCertificateId(certificateId ?? null);
    if (!certificateId) {
      setSelectedCertificate(null);
    }
    setSelectedDeviceId(null);
    setInstallModalOpen(true);
  };

  const handleInstall = async () => {
    const certId = installCertificateId ?? selectedCertificate?.id;
    if (!certId || !selectedDeviceId) {
      notify("Selecione certificado e dispositivo.", "error");
      return;
    }
    try {
      const response = await apiFetch(`/certificados/${certId}/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: selectedDeviceId }),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Falha ao criar job.", "error");
        return;
      }
      notify("Job de instalação criado com sucesso.");
      setInstallModalOpen(false);
      setInstallCertificateId(null);
      setSelectedDeviceId(null);
      loadJobs();
    } catch {
      notify("Falha ao criar job.", "error");
    }
  };

  const handleExport = () => {
    const rows = filteredCertificates.map((cert) => {
      const status = getStatusInfo(cert.not_after);
      return {
        Empresa: cert.name,
        Documento: extractTaxId(cert.subject ?? cert.name),
        Titular: cert.subject ?? cert.name,
        Serial: cert.serial_number ?? "-",
        SHA1: cert.sha1_fingerprint ?? "-",
        Validade: formatDate(cert.not_after),
        Status: status.label,
      };
    });
    const header = Object.keys(rows[0] ?? {
      Empresa: "",
      Documento: "",
      Titular: "",
      Serial: "",
      SHA1: "",
      Validade: "",
      Status: "",
    });
    const csv = [header.join(";"), ...rows.map((row) => header.map((key) => row[key as keyof typeof row]).join(";"))].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "certificados.csv";
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Certificados</h1>
        <p className="text-sm text-slate-500">
          Instalação controlada via Agent • Sem expor arquivo/senha • Remoção
          automática às 18:00
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        {kpis.map((kpi) => (
          <div
            key={kpi.label}
            className="rounded-3xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <p className="text-xs text-slate-500">{kpi.label}</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900">
              {kpi.value}
            </p>
            <p className="text-xs text-slate-400">{kpi.meta}</p>
          </div>
        ))}
      </div>

      <SectionTabs />

      <div className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-1 flex-col gap-3 md:flex-row md:items-center">
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
              className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 text-sm text-slate-600"
              placeholder="Buscar por empresa, CNPJ..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <select
            className="h-11 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option>Todos</option>
            <option>Válido</option>
            <option>Vence em 7d</option>
            <option>Vence em 30d</option>
            <option>Vencido</option>
          </select>
          <select
            className="h-11 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
            value={orderBy}
            onChange={(event) => setOrderBy(event.target.value)}
          >
            <option value="validade">Ordenar por validade</option>
            <option value="empresa">Ordenar por empresa</option>
          </select>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            className="flex h-11 items-center gap-2 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
            onClick={handleExport}
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
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <path d="M7 10 12 15 17 10" />
              <path d="M12 15V3" />
            </svg>
            Exportar
          </button>
          <button
            className="h-11 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white"
            onClick={() => handleOpenInstall()}
          >
            Instalar via Agent
          </button>
        </div>
      </div>

      {loading ? (
        <CertCardsGrid>
          {Array.from({ length: 6 }).map((_, index) => (
            <div
              key={`skeleton-${index}`}
              className="h-56 rounded-3xl border border-dashed border-slate-200 bg-white/70"
            />
          ))}
        </CertCardsGrid>
      ) : filteredCertificates.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
          Nenhum certificado encontrado para os filtros atuais.
        </div>
      ) : (
        <CertCardsGrid>
          {pagedCertificates.map((cert) => {
            const statusInfo = getStatusInfo(cert.not_after);
            const certStatus = mapStatusToCert(statusInfo.key);
            const taxDigits = extractDigits(cert.subject ?? cert.name);
            return (
              <CertCard
                key={cert.id}
                empresa={cert.name}
                cnpj={taxDigits}
                status={certStatus}
                validadeISO={toISODate(cert.not_after)}
                diasLabel={statusInfo.meta}
                titular={cert.subject ?? cert.name}
                serial={cert.serial_number ?? undefined}
                sha1={cert.sha1_fingerprint ?? undefined}
                footerUser={user?.ad_username ?? "CurrentUser"}
                onInstall={() => handleOpenInstall(cert.id)}
                onDetails={() => {
                  setSelectedCertificate(cert);
                  setDetailModalOpen(true);
                }}
              />
            );
          })}
        </CertCardsGrid>
      )}

      <div className="flex items-center justify-between text-sm text-slate-500">
        <span>
          Mostrando {pagedCertificates.length} de {filteredCertificates.length} certificados
        </span>
        <div className="flex items-center gap-2">
          <button
            className="h-9 rounded-2xl border border-slate-200 px-3 text-xs"
            disabled={page === 1}
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
          >
            Anterior
          </button>
          <span className="text-xs">
            {page} / {totalPages}
          </span>
          <button
            className="h-9 rounded-2xl border border-slate-200 px-3 text-xs"
            disabled={page === totalPages}
            onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
          >
            Próximo
          </button>
        </div>
      </div>

      <Modal
        title="Instalar certificado"
        open={installModalOpen}
        onClose={() => setInstallModalOpen(false)}
        footer={
          <>
            <button
              className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
              onClick={() => setInstallModalOpen(false)}
            >
              Cancelar
            </button>
            <button
              className="h-10 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white"
              onClick={handleInstall}
            >
              Confirmar instalação
            </button>
          </>
        }
      >
        {!installCertificateId && (
          <label className="block text-xs font-semibold text-slate-500">
            Certificado
            <select
              className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
              value={selectedCertificate?.id ?? ""}
              onChange={(event) => {
                const cert = certificates.find((item) => item.id === event.target.value) || null;
                setSelectedCertificate(cert);
              }}
            >
              <option value="">Selecione um certificado</option>
              {certificates.map((cert) => (
                <option key={cert.id} value={cert.id}>
                  {cert.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="block text-xs font-semibold text-slate-500">
          Dispositivo
          <select
            className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
            value={selectedDeviceId ?? ""}
            onChange={(event) => setSelectedDeviceId(event.target.value)}
          >
            <option value="">Selecione o device</option>
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.hostname} {device.domain ? `(${device.domain})` : ""}
              </option>
            ))}
          </select>
        </label>
        <div className="rounded-2xl bg-slate-50 p-4 text-xs text-slate-500">
          O Agent instalará o certificado no perfil do usuário selecionado. Jobs aprovados
          automaticamente por ADMIN/DEV ficam em "Pendente".
        </div>
      </Modal>

      <Modal
        title="Detalhes do certificado"
        open={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
      >
        {selectedCertificate ? (
          <div className="space-y-3">
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs text-slate-400">Empresa</p>
              <p className="mt-2 text-sm font-semibold text-slate-900">
                {selectedCertificate.name}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Documento: {extractTaxId(selectedCertificate.subject ?? selectedCertificate.name)}
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Titular</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedCertificate.subject ?? "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Emissor</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedCertificate.issuer ?? "-"}
                </p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Serial</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedCertificate.serial_number ?? "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">SHA1</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedCertificate.sha1_fingerprint ?? "-"}
                </p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Válido de</p>
                <p className="mt-2 text-sm text-slate-700">
                  {formatDate(selectedCertificate.not_before)}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Válido até</p>
                <p className="mt-2 text-sm text-slate-700">
                  {formatDate(selectedCertificate.not_after)}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <p>Selecione um certificado para ver detalhes.</p>
        )}
      </Modal>

      {toast && <Toast message={toast.message} tone={toast.tone} />}
    </div>
  );
};

export default CertificatesPage;
