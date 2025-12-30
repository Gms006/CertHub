export const extractDigits = (value?: string | null) =>
  value ? value.replace(/\D/g, "") : "";

export const formatCnpjCpf = (value?: string | null) => {
  const digits = extractDigits(value);
  if (digits.length === 11) {
    return digits.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
  }
  if (digits.length === 14) {
    return digits.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
  }
  return "-";
};

export const formatDate = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("pt-BR");
};

export const formatDateTime = (value?: string | null) => {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const datePart = date.toLocaleDateString("pt-BR");
  const timePart = date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  return `${datePart} ${timePart}`;
};

export const daysUntil = (value?: string | null) => {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.ceil((date.getTime() - Date.now()) / (1000 * 60 * 60 * 24));
};

export const sanitizeSensitiveLabel = (value?: string | null) => {
  if (!value) return "";
  let sanitized = value;
  const patterns = [
    /senha\s*[:=]?\s*[^\s]+/gi,
    /senha[_-]?[^\s]+/gi,
    /\bsenha\b/gi,
  ];
  patterns.forEach((pattern) => {
    sanitized = sanitized.replace(pattern, "");
  });
  sanitized = sanitized.replace(/[_-]{2,}/g, "-");
  sanitized = sanitized.replace(/\s{2,}/g, " ");
  sanitized = sanitized.replace(/[-_ ]+$/g, "");
  sanitized = sanitized.replace(/^[-_ ]+/g, "");
  return sanitized.trim();
};
