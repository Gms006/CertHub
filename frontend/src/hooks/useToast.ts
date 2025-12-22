import { useCallback, useEffect, useState } from "react";

type ToastState = {
  message: string;
  tone?: "success" | "error";
};

export const useToast = (timeoutMs = 3200) => {
  const [toast, setToast] = useState<ToastState | null>(null);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), timeoutMs);
    return () => clearTimeout(timer);
  }, [toast, timeoutMs]);

  const notify = useCallback((message: string, tone: ToastState["tone"] = "success") => {
    setToast({ message, tone });
  }, []);

  return { toast, notify, clear: () => setToast(null) };
};
