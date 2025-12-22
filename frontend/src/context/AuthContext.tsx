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
  ad_username?: string;
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
  initializing: boolean;
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
    sessionStorage.getItem("certhub_access_token"),
  );
  const [user, setUser] = useState<AuthUser | null>(() => {
    const raw = sessionStorage.getItem("certhub_user");
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  });
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const persistUser = (nextUser: AuthUser | null, token: string | null) => {
    if (token) {
      sessionStorage.setItem("certhub_access_token", token);
    } else {
      sessionStorage.removeItem("certhub_access_token");
    }
    if (nextUser) {
      sessionStorage.setItem("certhub_user", JSON.stringify(nextUser));
    } else {
      sessionStorage.removeItem("certhub_user");
    }
  };

  const clearAuth = useCallback(() => {
    setAccessToken(null);
    setUser(null);
    persistUser(null, null);
  }, []);

  const refreshAccessToken = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
      });

      const data = await parseJson<{ access_token: string }>(response);
      
      setAccessToken(data.access_token);
      localStorage.setItem("certhub_access_token", data.access_token); // só token

      return data.access_token;
    } catch {
      clearAuth();
      return null;
    }
  }, [clearAuth]);
  const apiFetch = useMemo(
    () =>
      createApiClient({
        getAccessToken: () => accessToken,
        refreshAccessToken,
        onUnauthorized: () => {
          clearAuth();
          window.location.assign("/login");
        },
      }),
    [accessToken, clearAuth, refreshAccessToken],
  );

  const fetchCurrentUser = useCallback(
    async (token: string) => {
      const response = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      const data = await parseJson<AuthUser>(response);
      setUser(data);
      persistUser(data, token);
      return data;
    },
    [],
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
      clearAuth();
      setLoading(false);
      window.location.assign("/login");
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
    const initialize = async () => {
      try {
        if (accessToken) {
          await fetchCurrentUser(accessToken);
        } else {
          const token = await refreshAccessToken();
          if (token) {
            await fetchCurrentUser(token);
          }
        }
      } catch {
        clearAuth();
      } finally {
        setInitializing(false);
      }
    };
    initialize();
  }, [accessToken, clearAuth, fetchCurrentUser, refreshAccessToken]);

  const value: AuthContextValue = {
    user,
    accessToken,
    loading,
    initializing,
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
