import { useEffect, useMemo, useState } from "react";

import { useAuth } from "../hooks/useAuth";

type CertificateCard = {
  id: string;
  company: string;
  cnpj: string;
  holder: string;
  serial: string;
  sha1: string;
  validUntil: string;
  status: "valid" | "expiring7" | "expiring30" | "expired";
  statusLabel: string;
  statusMeta: string;
};

const mockCertificates: CertificateCard[] = [
  {
    id: "1",
    company: "ADAHYL CHAVEIRO ADVOGADOS",
    cnpj: "11.223.344/0001-55",
    holder: "ADAHYL CHAVEIRO ADVO...",
    serial: "00EF12AA",
    sha1: "A0:02...C2",
    validUntil: "2025-10-10",
    status: "expired",
    statusLabel: "Vencido",
    statusMeta: "68 dias atrasado",
  },
  {
    id: "2",
    company: "TRADIÇÃO COMÉRCIO E SERVIÇO",
    cnpj: "04.292.064/0001-64",
    holder: "TRADIÇÃO COMÉRCIO E S...",
    serial: "19AFE21",
    sha1: "11:8C...9D",
    validUntil: "2025-12-21",
    status: "expiring7",
    statusLabel: "Vence em 7d",
    statusMeta: "4 dias",
  },
  {
    id: "3",
    company: "F E ARANTES LTDA",
    cnpj: "12.345.678/0001-90",
    holder: "F E ARANTES LTDA",
    serial: "0A1B2C3D",
    sha1: "9A:2E...F1",
    validUntil: "2026-02-08",
    status: "expiring30",
    statusLabel: "Vence em 30d",
    statusMeta: "53 dias",
  },
  {
    id: "4",
    company: "JC ESTOFADOS LTDA",
    cnpj: "55.667.788/0001-22",
    holder: "JC ESTOFADOS LTDA",
    serial: "88DD11EF",
    sha1: "77:3D...C8",
    validUntil: "2026-06-30",
    status: "valid",
    statusLabel: "Válido",
    statusMeta: "195 dias",
  },
];

const statusStyles: Record<
  CertificateCard["status"],
  { badge: string; dot: string }
> = {
  valid: {
    badge: "bg-emerald-50 text-emerald-700",
    dot: "bg-emerald-500",
  },
  expiring7: {
    badge: "bg-amber-50 text-amber-700",
    dot: "bg-amber-500",
  },
  expiring30: {
    badge: "bg-sky-50 text-sky-700",
    dot: "bg-sky-500",
  },
  expired: {
    badge: "bg-rose-50 text-rose-700",
    dot: "bg-rose-500",
  },
};

const toStatus = (notAfter?: string | null): CertificateCard["status"] => {
  if (!notAfter) return "valid";
  const expiry = new Date(notAfter).getTime();
  const diffDays = Math.ceil((expiry - Date.now()) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) return "expired";
  if (diffDays <= 7) return "expiring7";
  if (diffDays <= 30) return "expiring30";
  return "valid";
};

const CertificatesPage = () => {
  const { apiFetch } = useAuth();
  const [certificates, setCertificates] =
    useState<CertificateCard[]>(mockCertificates);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await apiFetch("/certificados");
        if (!response.ok) {
          return;
        }
        const data = (await response.json()) as {
          id: string;
          name: string;
          subject?: string | null;
          serial_number?: string | null;
          sha1_fingerprint?: string | null;
          not_after?: string | null;
        }[];
        const mapped = data.map((item) => {
          const status = toStatus(item.not_after ?? null);
          return {
            id: item.id,
            company: item.name,
            cnpj: "00.000.000/0000-00",
            holder: item.subject ?? item.name,
            serial: item.serial_number ?? "-",
            sha1: item.sha1_fingerprint ?? "-",
            validUntil: item.not_after ?? "-",
            status,
            statusLabel:
              status === "valid"
                ? "Válido"
                : status === "expired"
                  ? "Vencido"
                  : status === "expiring7"
                    ? "Vence em 7d"
                    : "Vence em 30d",
            statusMeta:
              status === "expired"
                ? "Expirado"
                : status === "expiring7"
                  ? "7 dias"
                  : status === "expiring30"
                    ? "30 dias"
                    : "OK",
          };
        });
        if (mapped.length) {
          setCertificates(mapped);
        }
      } catch {
        // mantém mock caso falhe
      }
    };
    load();
  }, [apiFetch]);

  const kpis = useMemo(
    () => [
      { label: "Certificados", value: "4", meta: "catalogados no DB" },
      { label: "Vencidos", value: "1", meta: "exigem ação" },
      { label: "Vence em 7d", value: "1", meta: "prioridade" },
      { label: "Jobs ativos", value: "1", meta: "pendente/progresso" },
      { label: "Devices OK", value: "2", meta: "autorizados" },
    ],
    [],
  );

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

      <div className="flex flex-wrap gap-3 text-sm font-medium text-slate-500">
        {["Certificados", "Jobs", "Dispositivos", "Auditoria"].map((tab) => (
          <button
            key={tab}
            className={`rounded-full px-4 py-2 ${
              tab === "Certificados"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

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
            />
          </div>
          <select className="h-11 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600">
            <option>Todos</option>
            <option>Vencidos</option>
            <option>Vence em 7d</option>
          </select>
          <select className="h-11 rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-600">
            <option>Ordenar por validade</option>
            <option>Ordenar por empresa</option>
          </select>
        </div>
        <div className="flex flex-wrap gap-3">
          <button className="flex h-11 items-center gap-2 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600">
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
          <button className="h-11 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white">
            Instalar via Agent
          </button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {certificates.map((cert) => {
          const styles = statusStyles[cert.status];
          return (
            <div
              key={cert.id}
              className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-100 text-slate-500">
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
                      <path d="M12 2 5 5v6c0 5.25 3.44 10 7 11 3.56-1 7-5.75 7-11V5l-7-3Z" />
                    </svg>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-slate-900">
                      {cert.company}
                    </p>
                    <p className="text-xs text-slate-400">CNPJ: {cert.cnpj}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${styles.badge}`}
                  >
                    {cert.statusLabel}
                  </span>
                  <span className="flex items-center gap-1 text-[11px] text-slate-400">
                    <span
                      className={`h-2 w-2 rounded-full ${styles.dot}`}
                    />
                    {cert.statusMeta}
                  </span>
                </div>
              </div>

              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-400">Titular</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {cert.holder}
                  </p>
                </div>
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-400">Identificadores</p>
                  <p className="mt-2 text-sm text-slate-700">
                    Serial: {cert.serial}
                  </p>
                  <p className="mt-1 text-sm text-slate-700">SHA1: {cert.sha1}</p>
                </div>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button className="h-10 rounded-2xl bg-[#0e2659] px-4 text-sm font-semibold text-white">
                  Instalar
                </button>
                <button className="h-10 rounded-2xl border border-slate-200 px-4 text-sm text-slate-600">
                  Detalhes
                </button>
                <div className="ml-auto flex items-center text-xs text-slate-400">
                  Validade: {cert.validUntil}
                </div>
              </div>

              <p className="mt-4 text-xs text-slate-400">
                Instalação via Agent (CurrentUser). Certificados temporários serão
                removidos automaticamente às 18:00.
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default CertificatesPage;
