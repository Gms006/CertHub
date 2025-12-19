import { useState } from "react";

import { API_BASE } from "../lib/api";

type AuthUser = {
  id: string;
  email: string | null;
  nome?: string | null;
  role_global?: string;
};

type LoginResponse = {
  access_token: string;
  refresh_token?: string | null;
  user: AuthUser;
};

type MessageResponse = {
  message: string;
  token?: string | null;
  expires_at?: string | null;
};

const parseJson = async <T,>(response: Response): Promise<T> => {
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail ?? "Erro inesperado.";
    throw new Error(detail);
  }
  return data;
};

export const useAuth = () => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const login = async (email: string, password: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      const data = await parseJson<LoginResponse>(response);
      localStorage.setItem("certhub_access_token", data.access_token);
      localStorage.setItem("certhub_user", JSON.stringify(data.user));
      setMessage("Login realizado com sucesso.");
      return data;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha no login.");
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const setPassword = async (token: string, newPassword: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/auth/password/set/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      const data = await parseJson<MessageResponse>(response);
      setMessage(data.message);
      return data;
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Falha ao definir senha.",
      );
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const resetPasswordInit = async (email: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/auth/password/reset/init`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ email }),
      });
      const data = await parseJson<MessageResponse>(response);
      setMessage(data.message);
      return data;
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Falha ao iniciar reset.",
      );
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const resetPasswordConfirm = async (token: string, newPassword: string) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/auth/password/reset/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ token, new_password: newPassword }),
      });
      const data = await parseJson<MessageResponse>(response);
      setMessage(data.message);
      return data;
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Falha ao resetar senha.",
      );
      throw error;
    } finally {
      setLoading(false);
    }
  };

  return {
    loading,
    message,
    login,
    setPassword,
    resetPasswordInit,
    resetPasswordConfirm,
  };
};
