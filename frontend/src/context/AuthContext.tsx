import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { API_BASE, createApiClient } from "../lib/apiClient";

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

type AuthContextValue = {
  user: AuthUser | null;
  accessToken: string | null;
  loading: boolean;
  message: string | null;
  login: (email: string, password: string) => Promise<LoginResponse | null>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<string | null>;
  setPassword: (token: string, newPassword: string) => Promise<MessageResponse>;
  resetPasswordInit: (email: string) => Promise<MessageResponse>;
  resetPasswordConfirm: (token: string, newPassword: string) => Promise<MessageResponse>;
  apiFetch: ReturnType<typeof createApiClient>;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

const parseJson = async <T,>(response: Response): Promise<T> => {
  const data = await response.json();
  if (!response.ok) {
    const detail = data?.detail ?? "Erro inesperado.";
    throw new Error(detail);
  }
  return data;
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    localStorage.getItem("certhub_access_token"),
  );
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = localStorage.getItem("certhub_user");
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const persistUser = (nextUser: AuthUser | null, token: string | null) => {
    if (token) {
      localStorage.setItem("certhub_access_token", token);
    } else {
      localStorage.removeItem("certhub_access_token");
    }
    if (nextUser) {
      localStorage.setItem("certhub_user", JSON.stringify(nextUser));
    } else {
      localStorage.removeItem("certhub_user");
    }
  };

  const refreshAccessToken = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
      const data = await parseJson<{ access_token: string }>(response);
      setAccessToken(data.access_token);
      persistUser(user, data.access_token);
      return data.access_token;
    } catch {
      setAccessToken(null);
      persistUser(user, null);
      return null;
    }
  }, [user]);

  const apiFetch = useMemo(
    () =>
      createApiClient({
        getAccessToken: () => accessToken,
        refreshAccessToken,
      }),
    [accessToken, refreshAccessToken],
  );

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
      setAccessToken(data.access_token);
      setUser(data.user);
      persistUser(data.user, data.access_token);
      setMessage("Login realizado com sucesso.");
      return data;
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Falha no login.");
      return null;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    setMessage(null);
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });
    } finally {
      setAccessToken(null);
      setUser(null);
      persistUser(null, null);
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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!accessToken) {
      refreshAccessToken();
    }
  }, [accessToken, refreshAccessToken]);

  const value: AuthContextValue = {
    user,
    accessToken,
    loading,
    message,
    login,
    logout,
    refreshAccessToken,
    setPassword,
    resetPasswordInit,
    resetPasswordConfirm,
    apiFetch,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
};
