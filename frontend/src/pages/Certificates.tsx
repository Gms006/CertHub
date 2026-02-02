import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownWideNarrow,
  BadgeCheck,
  CalendarClock,
  Download,
  FileBadge2,
  Info,
  KeyRound,
  MonitorCheck,
  Search,
  ShieldAlert,
  XCircle,
} from "lucide-react";

import Modal from "../components/Modal";
import SectionTabs from "../components/SectionTabs";
import Toast from "../components/Toast";
import { useAuth } from "../hooks/useAuth";
import { usePreferences } from "../hooks/usePreferences";
import { useToast } from "../hooks/useToast";
import {
  daysUntil,
  extractDigits,
  formatDate,
  sanitizeSensitiveLabel,
} from "../lib/formatters";

type CertificateRead = {
  id: string;
  name: string;
  cn?: string | null;
  issuer_cn?: string | null;
  document_type?: "CNPJ" | "CPF" | null;
  document_masked?: string | null;
  document_unmasked?: string | null;
  serial_number?: string | null;
  sha1_fingerprint?: string | null;
  parse_ok?: boolean;
  parse_error?: string | null;
  last_ingested_at?: string | null;
  last_error_at?: string | null;
  not_after?: string | null;
  not_before?: string | null;
  created_at: string;
};

type CertificateTechnicalRead = {
  id: string;
  name: string;
  subject?: string | null;
  issuer?: string | null;
};

type DeviceRead = {
  id: string;
  hostname: string;
  domain?: string | null;
  agent_version?: string | null;
  last_seen_at?: string | null;
  is_allowed?: boolean;
  allow_keep_until?: boolean;
  allow_exempt?: boolean;
  assigned_user?: {
    id: string;
    ad_username: string;
    email?: string | null;
    nome?: string | null;
  } | null;
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

const formatDocument = (value: string) => value || "-";

const formatCpf = (digits: string) =>
  `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9, 11)}`;

const formatCnpj = (digits: string) =>
  `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(
    8,
    12,
  )}-${digits.slice(12, 14)}`;

const buildMaskedDocument = (cert: CertificateRead) => {
  const unmasked = cert.document_unmasked?.trim() ?? "";
  const digits = extractDigits((unmasked || cert.document_masked) ?? "");

  if (digits.length === 11) {
    return `CPF ${formatCpf(digits)}`;
  }

  if (digits.length === 14) {
    return `CNPJ ${formatCnpj(digits)}`;
  }

  const maskedValue = cert.document_masked?.trim() ?? "";
  const cleanedValue = maskedValue.replace(/\*/g, "").trim();
  if (cleanedValue) {
    const inferredType = cert.document_type || (cleanedValue.startsWith("CPF") ? "CPF" : cleanedValue.startsWith("CNPJ") ? "CNPJ" : null);
    if (inferredType && !cleanedValue.startsWith(inferredType)) {
      return `${inferredType} ${cleanedValue}`;
    }
    return cleanedValue;
  }

  return "-";
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
                Documento: {cnpj}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-col gap-2">
            <button
              onClick={onInstall}
              className="inline-flex h-9 w-[120px] items-center justify-center gap-2 rounded-2xl bg-slate-900 px-3 text-xs font-semibold text-white hover:bg-slate-800"
            >
              <KeyRound className="h-4 w-4" />
              Instalar
            </button>

            <button
              onClick={onDetails}
              className="inline-flex h-9 w-[120px] items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              <Info className="h-4 w-4" />
              Detalhes
            </button>
          </div>
        </div>

        <div className="mt-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <StatusIcon className={`h-4 w-4 ${ui.iconClass}`} />
            <span
              className={`inline-flex max-w-full items-center truncate rounded-full px-2.5 py-1 text-xs font-semibold ${ui.badgeClass}`}
            >
              {ui.label}
            </span>
          </div>

          <span className="inline-flex max-w-full items-center truncate rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700">
            Validade: {validadeISO}
          </span>
        </div>

        {diasLabel ? (
          <div className="mt-2">
            <span className="inline-flex max-w-full items-center truncate rounded-full bg-slate-100 px-2 py-1 text-[11px] font-semibold text-slate-700">
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
              <span className="break-words">{serial || "-"}</span>
            </div>
            <div className="mt-1 text-[11px] text-slate-600">
              <span className="font-semibold text-slate-700">SHA1:</span>{" "}
              <span className="break-words">{sha1 || "-"}</span>
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

const getCertificateDisplayName = (cert: CertificateRead) => {
  const rawName = cert.cn || sanitizeSensitiveLabel(cert.name);
  const separatorIndex = rawName.lastIndexOf(":");
  const base = separatorIndex > -1 ? rawName.slice(0, separatorIndex).trim() : rawName;
  const trimmed = base.replace(
    /(?:\s+|:)(\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2})$/,
    "",
  );
  return trimmed.trim() || base || rawName;
};

const getCertificateDocument = (cert: CertificateRead) => buildMaskedDocument(cert);

const CertificatesPage = () => {
  const { apiFetch, user } = useAuth();
  const { preferences } = usePreferences();
  const { toast, notify } = useToast();
  const [certificates, setCertificates] = useState<CertificateRead[]>([]);
  const [devices, setDevices] = useState<DeviceRead[]>([]);
  const [jobs, setJobs] = useState<InstallJobRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("Todos");
  const [orderBy, setOrderBy] = useState(preferences.defaultOrder);
  const [hideExpired, setHideExpired] = useState(true);
  const [page, setPage] = useState(1);
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [installCertificateId, setInstallCertificateId] = useState<string | null>(null);
  const [selectedCertificate, setSelectedCertificate] = useState<CertificateRead | null>(null);
  const [technicalCertificate, setTechnicalCertificate] =
    useState<CertificateTechnicalRead | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string | null>(null);
  const [cleanupMode, setCleanupMode] = useState<"DEFAULT" | "KEEP_UNTIL" | "EXEMPT">(
    "DEFAULT",
  );
  const [keepUntil, setKeepUntil] = useState("");
  const [keepReason, setKeepReason] = useState("");
  const pageSize = preferences.pageSize;
  const role = user?.role_global ?? "VIEW";
  const isAdmin = role === "ADMIN" || role === "DEV";
  const isView = role === "VIEW";
  const keepUntilMaxHours = user?.retention_keep_until_max_hours ?? null;

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

  useEffect(() => {
    if (!detailModalOpen || !selectedCertificate || !isAdmin) {
      setTechnicalCertificate(null);
      return;
    }
    const loadTechnical = async () => {
      try {
        const response = await apiFetch(`/certificados/${selectedCertificate.id}/technical`);
        if (!response.ok) {
          setTechnicalCertificate(null);
          return;
        }
        const data = (await response.json()) as CertificateTechnicalRead;
        setTechnicalCertificate(data);
      } catch {
        setTechnicalCertificate(null);
      }
    };
    loadTechnical();
  }, [apiFetch, detailModalOpen, isAdmin, selectedCertificate]);

  const loadDevices = async () => {
    const endpoint = isAdmin ? "/admin/devices" : "/devices/mine";
    try {
      const response = await apiFetch(endpoint);
      if (!response.ok) {
        return;
      }
      const data = (await response.json()) as DeviceRead[];
      setDevices(
        data.map((device) => ({
          ...device,
          allow_keep_until: device.allow_keep_until ?? true,
          allow_exempt: device.allow_exempt ?? true,
        })),
      );
    } catch {
      // silencioso
    }
  };

  const loadJobs = async () => {
    const isAdmin = user?.role_global === "ADMIN" || user?.role_global === "DEV";
    const endpoint = isAdmin
      ? "/install-jobs"
      : user?.role_global === "VIEW"
        ? "/install-jobs?scope=my-device"
        : "/install-jobs?scope=mine";
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
  }, [isAdmin]);

  useEffect(() => {
    loadJobs();
  }, [user?.role_global]);

  useEffect(() => {
    setOrderBy(preferences.defaultOrder);
  }, [preferences.defaultOrder]);

  useEffect(() => {
    if (!isView || !devices.length) return;
    if (selectedDeviceId) return;
    if (
      preferences.defaultDeviceId &&
      devices.some((device) => device.id === preferences.defaultDeviceId)
    ) {
      setSelectedDeviceId(preferences.defaultDeviceId);
      return;
    }
    if (devices.length === 1) {
      setSelectedDeviceId(devices[0].id);
    }
  }, [devices, isView, preferences.defaultDeviceId, selectedDeviceId]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, orderBy, hideExpired]);

  const filteredCertificates = useMemo(() => {
    const term = search.trim().toLowerCase();
    const filtered = certificates.filter((cert) => {
      const safeName = sanitizeSensitiveLabel(cert.name);
      const status = getStatusInfo(cert.not_after).key;
      if (hideExpired && status === "expired") {
        return false;
      }
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
      const displayName = getCertificateDisplayName(cert);
      const taxId = extractDigits(cert.document_masked ?? "");
      const haystack = [
        displayName,
        safeName,
        cert.serial_number,
        cert.sha1_fingerprint,
        taxId,
        cert.document_masked,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(term);
    });

    const sorted = [...filtered].sort((a, b) => {
      if (orderBy === "empresa") {
        const aName = getCertificateDisplayName(a);
        const bName = getCertificateDisplayName(b);
        return aName.localeCompare(bName);
      }
      const aTime = a.not_after ? new Date(a.not_after).getTime() : Number.MAX_SAFE_INTEGER;
      const bTime = b.not_after ? new Date(b.not_after).getTime() : Number.MAX_SAFE_INTEGER;
      return aTime - bTime;
    });

    return sorted;
  }, [certificates, hideExpired, orderBy, search, statusFilter]);

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
      {
        label: "Certificados",
        value: `${certificates.length}`,
        meta: "catalogados no DB",
        icon: KeyRound,
      },
      {
        label: "Vencidos",
        value: `${expiredCount}`,
        meta: "exigem ação",
        icon: ShieldAlert,
      },
      {
        label: "Vence em 7d",
        value: `${expiring7Count}`,
        meta: "prioridade",
        icon: CalendarClock,
      },
      {
        label: "Jobs ativos",
        value: `${jobs.length}`,
        meta: "pendente/progresso",
        icon: Activity,
      },
      {
        label: "Devices OK",
        value: `${devices.filter((d) => d.is_allowed).length}`,
        meta: "autorizados",
        icon: MonitorCheck,
      },
    ];
  }, [certificates, devices, jobs]);

  const availableDevices = useMemo(() => devices, [devices]);
  const selectedDevice = useMemo(
    () => devices.find((device) => device.id === selectedDeviceId) ?? null,
    [devices, selectedDeviceId],
  );
  const deviceAllowsKeepUntil = selectedDevice?.allow_keep_until ?? true;
  const deviceAllowsExempt = selectedDevice?.allow_exempt ?? true;
  const showKeepUntilOption = Boolean(selectedDevice && deviceAllowsKeepUntil);
  const showExemptOption = Boolean(selectedDevice && deviceAllowsExempt);

  useEffect(() => {
    if (!selectedDevice) {
      return;
    }
    const keepUntilAllowed = deviceAllowsKeepUntil;
    const exemptAllowed = deviceAllowsExempt && roleAllowsExempt;
    if (cleanupMode === "KEEP_UNTIL" && !keepUntilAllowed) {
      setCleanupMode("DEFAULT");
      setKeepUntil("");
      setKeepReason("");
      return;
    }
    if (cleanupMode === "EXEMPT" && !exemptAllowed) {
      setCleanupMode("DEFAULT");
      setKeepUntil("");
      setKeepReason("");
    }
  }, [
    cleanupMode,
    deviceAllowsExempt,
    deviceAllowsKeepUntil,
    roleAllowsExempt,
    selectedDevice,
  ]);

  const handleOpenInstall = (certificateId?: string) => {
    setInstallCertificateId(certificateId ?? null);
    if (!certificateId) {
      setSelectedCertificate(null);
    }
    setSelectedDeviceId(null);
    setCleanupMode("DEFAULT");
    setKeepUntil("");
    setKeepReason("");
    setInstallModalOpen(true);
  };

  const handleInstall = async () => {
    const certId = installCertificateId ?? selectedCertificate?.id;
    if (!certId || !selectedDeviceId) {
      notify("Selecione certificado e dispositivo.", "error");
      return;
    }
    if (cleanupMode === "KEEP_UNTIL" && !keepUntil) {
      notify("Informe a data/hora para manter o certificado.", "error");
      return;
    }
    if (cleanupMode === "EXEMPT" && !keepReason.trim()) {
      notify("Informe o motivo da isenção de cleanup.", "error");
      return;
    }
    try {
      const payload: Record<string, string> = {
        device_id: selectedDeviceId,
        cleanup_mode: cleanupMode,
      };
      if (cleanupMode === "KEEP_UNTIL") {
        const parsedDate = new Date(keepUntil);
        if (Number.isNaN(parsedDate.getTime())) {
          notify("Data/hora inválida para retenção.", "error");
          return;
        }
        payload.keep_until = parsedDate.toISOString();
      }
      if (cleanupMode === "EXEMPT") {
        payload.keep_reason = keepReason.trim();
      }
      const response = await apiFetch(`/certificados/${certId}/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const data = (await response.json()) as { detail?: string };
        notify(data?.detail ?? "Falha ao criar job.", "error");
        if (response.status === 400 || response.status === 403) {
          setCleanupMode("DEFAULT");
          setKeepUntil("");
          setKeepReason("");
        }
        return;
      }
      notify("Job de instalação criado com sucesso.");
      setInstallModalOpen(false);
      setInstallCertificateId(null);
      setSelectedDeviceId(null);
      setCleanupMode("DEFAULT");
      setKeepUntil("");
      setKeepReason("");
      loadJobs();
    } catch {
      notify("Falha ao criar job.", "error");
    }
  };

  const handleExport = async () => {
    try {
      const response = await apiFetch("/certificados/export/excel");
      if (!response.ok) {
        notify("Não foi possível exportar os certificados.", "error");
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "certificados.xlsx";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      notify("Erro ao exportar os certificados.", "error");
    }
  };

  const selectedCert = installCertificateId
    ? certificates.find((cert) => cert.id === installCertificateId) ?? null
    : selectedCertificate;

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
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs text-slate-500">{kpi.label}</p>
              <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-50 text-slate-600">
                <kpi.icon className="h-4 w-4" />
              </span>
            </div>
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
              <Search className="h-4 w-4" />
            </span>
            <input
              className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 text-sm text-slate-600"
              placeholder="Buscar por empresa, CNPJ..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <CalendarClock className="h-4 w-4" />
            </span>
            <select
              className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 pr-4 text-sm text-slate-600 appearance-none"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>Todos</option>
              <option>Válido</option>
              <option>Vence em 7d</option>
              <option>Vence em 30d</option>
              <option>Vencido</option>
            </select>
          </div>
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
              <ArrowDownWideNarrow className="h-4 w-4" />
            </span>
            <select
              className="h-11 w-full rounded-2xl border border-slate-200 bg-white pl-9 pr-4 text-sm text-slate-600 appearance-none"
              value={orderBy}
              onChange={(event) =>
                setOrderBy(event.target.value as "validade" | "empresa")
              }
            >
              <option value="validade">Ordenar por validade</option>
              <option value="empresa">Ordenar por empresa</option>
            </select>
          </div>
          <label className="inline-flex h-11 items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 text-xs font-semibold text-slate-600">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={hideExpired}
              onChange={(event) => setHideExpired(event.target.checked)}
            />
            Ocultar vencidos
          </label>
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            className="flex h-11 items-center gap-2 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600"
            onClick={handleExport}
          >
            <Download className="h-4 w-4" />
            Exportar
          </button>
          <button
            className="inline-flex h-11 items-center gap-2 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white whitespace-nowrap"
            onClick={() => handleOpenInstall()}
          >
            <KeyRound className="h-4 w-4" />
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
            const safeName = sanitizeSensitiveLabel(cert.name);
            const empresaName = getCertificateDisplayName(cert) || safeName;
            const documentValue = getCertificateDocument(cert);
            return (
              <CertCard
                key={cert.id}
                empresa={empresaName}
                cnpj={documentValue}
                status={certStatus}
                validadeISO={toISODate(cert.not_after)}
                diasLabel={statusInfo.meta}
                titular={empresaName}
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
        <div className="space-y-4">
          <div className="rounded-2xl border border-amber-100 bg-amber-50/70 p-4 text-xs text-amber-700">
            <p className="font-semibold">Aviso de segurança</p>
            <p className="mt-1">
              O arquivo e a senha não serão expostos no navegador. O Agent fará a
              importação em CurrentUser. Remoção automática às 18:00.
            </p>
          </div>

          {selectedCert ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-slate-900">
                    {sanitizeSensitiveLabel(selectedCert.name)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Documento: {getCertificateDocument(selectedCert)}
                  </p>
                </div>

                {(() => {
                  const info = getStatusInfo(selectedCert.not_after);
                  const badge =
                    info.key === "expired"
                      ? "bg-rose-50 text-rose-700"
                      : info.key === "expiring7"
                        ? "bg-amber-50 text-amber-700"
                        : "bg-emerald-50 text-emerald-700";
                  return (
                    <span
                      className={`inline-flex items-center whitespace-nowrap rounded-full px-3 py-1 text-xs font-semibold ${badge}`}
                    >
                      {info.label}
                    </span>
                  );
                })()}
              </div>

              <div className="mt-3 flex items-center justify-between text-xs text-slate-500">
                <span>Validade</span>
                <span className="font-semibold text-slate-700">
                  {formatDate(selectedCert.not_after)}
                </span>
              </div>
            </div>
          ) : null}

          {!installCertificateId && (
            <label className="block text-xs font-semibold text-slate-500">
              Certificado
              <select
                className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
                value={selectedCertificate?.id ?? ""}
                onChange={(event) => {
                  const cert =
                    certificates.find((item) => item.id === event.target.value) ||
                    null;
                  setSelectedCertificate(cert);
                }}
              >
                <option value="">Selecione um certificado</option>
                {certificates.map((cert) => (
                  <option key={cert.id} value={cert.id}>
                    {sanitizeSensitiveLabel(cert.name)}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-xs font-semibold text-slate-500">
            Selecione o dispositivo
            <select
              className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
              value={selectedDeviceId ?? ""}
              onChange={(event) => setSelectedDeviceId(event.target.value)}
            >
              <option value="">Selecione o device</option>
              {availableDevices.map((device) => {
                const userLabel =
                  device.assigned_user?.ad_username ||
                  device.assigned_user?.email ||
                  "";
                return (
                  <option key={device.id} value={device.id}>
                    {device.hostname}
                    {userLabel ? ` • ${userLabel}` : ""}
                  </option>
                );
              })}
            </select>
          </label>

          <label className="block text-xs font-semibold text-slate-500">
            Política de retenção
            <select
              className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
              value={cleanupMode}
              onChange={(event) =>
                setCleanupMode(event.target.value as "DEFAULT" | "KEEP_UNTIL" | "EXEMPT")
              }
            >
              <option value="DEFAULT">Remover às 18:00 (padrão)</option>
              {showKeepUntilOption && (
                <option value="KEEP_UNTIL">Manter até data/hora</option>
              )}
              {showExemptOption && (
                <option value="EXEMPT">Isento de cleanup automático</option>
              )}
            </select>
          </label>

          {isAdmin && selectedDevice ? (
            <div className="text-[11px] text-slate-500">
              {!deviceAllowsKeepUntil ? (
                <p>Keep Until: Não permitido para este dispositivo.</p>
              ) : null}
              {!deviceAllowsExempt ? (
                <p>Exempt: Não permitido para este dispositivo.</p>
              ) : null}
            </div>
          ) : null}

          {cleanupMode === "KEEP_UNTIL" ? (
            <label className="block text-xs font-semibold text-slate-500">
              Manter até
              <input
                type="datetime-local"
                className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600"
                value={keepUntil}
                onChange={(event) => setKeepUntil(event.target.value)}
              />
              {isView && keepUntilMaxHours ? (
                <span className="mt-2 block text-[11px] font-medium text-amber-600">
                  Aviso: período máximo permitido para VIEW é de{" "}
                  {keepUntilMaxHours} {keepUntilMaxHours === 1 ? "hora" : "horas"}.
                </span>
              ) : null}
            </label>
          ) : null}

          {cleanupMode === "EXEMPT" ? (
            <label className="block text-xs font-semibold text-slate-500">
              Motivo da isenção
              <textarea
                className="mt-2 min-h-[96px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600"
                value={keepReason}
                onChange={(event) => setKeepReason(event.target.value)}
              />
            </label>
          ) : null}

          <p className="text-[11px] text-slate-500">
            Dica: dispositivos “bloqueados” não receberão payload do job.
          </p>
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
                {getCertificateDisplayName(selectedCertificate)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Documento: {getCertificateDocument(selectedCertificate)}
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Titular</p>
                <p className="mt-2 text-sm text-slate-700">
                  {getCertificateDisplayName(selectedCertificate)}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Emissor</p>
                <p className="mt-2 text-sm text-slate-700">
                  {selectedCertificate.issuer_cn ?? "-"}
                </p>
              </div>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">Serial</p>
                <p className="mt-2 break-words text-sm text-slate-700">
                  {selectedCertificate.serial_number ?? "-"}
                </p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs text-slate-400">SHA1</p>
                <p className="mt-2 break-words text-sm text-slate-700">
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
            {isAdmin && technicalCertificate ? (
              <div className="rounded-2xl border border-slate-200 bg-white p-4 text-xs text-slate-600">
                <p className="text-[11px] font-semibold text-slate-500">
                  Detalhes técnicos (Admin/Dev)
                </p>
                <p className="mt-2">
                  <span className="font-semibold text-slate-700">Subject:</span>{" "}
                  {technicalCertificate.subject ?? "-"}
                </p>
                <p className="mt-2">
                  <span className="font-semibold text-slate-700">Issuer:</span>{" "}
                  {technicalCertificate.issuer ?? "-"}
                </p>
              </div>
            ) : null}
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
