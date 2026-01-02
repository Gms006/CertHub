import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type Preferences = {
  pageSize: number;
  defaultOrder: "validade" | "empresa";
  autoRefreshJobs: boolean;
  autoRefreshAudit: boolean;
  hideLongIds: boolean;
  defaultDeviceId: string;
};

type PreferencesContextValue = {
  preferences: Preferences;
  updatePreferences: (next: Partial<Preferences>) => void;
};

const DEFAULT_PREFERENCES: Preferences = {
  pageSize: 9,
  defaultOrder: "validade",
  autoRefreshJobs: false,
  autoRefreshAudit: false,
  hideLongIds: false,
  defaultDeviceId: "",
};

const STORAGE_KEY = "certhub_preferences";

const PreferencesContext = createContext<PreferencesContextValue | null>(null);

const loadPreferences = (): Preferences => {
  if (typeof window === "undefined") {
    return DEFAULT_PREFERENCES;
  }
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_PREFERENCES;
    const parsed = JSON.parse(stored) as Partial<Preferences>;
    return {
      ...DEFAULT_PREFERENCES,
      ...parsed,
      pageSize: parsed.pageSize ? Number(parsed.pageSize) : DEFAULT_PREFERENCES.pageSize,
    };
  } catch {
    return DEFAULT_PREFERENCES;
  }
};

export const PreferencesProvider = ({ children }: { children: ReactNode }) => {
  const [preferences, setPreferences] = useState<Preferences>(loadPreferences);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  const updatePreferences = useCallback((next: Partial<Preferences>) => {
    setPreferences((prev) => ({ ...prev, ...next }));
  }, []);

  const value = useMemo(
    () => ({ preferences, updatePreferences }),
    [preferences, updatePreferences],
  );

  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
};

export const usePreferences = () => {
  const context = useContext(PreferencesContext);
  if (!context) {
    throw new Error("usePreferences must be used within PreferencesProvider");
  }
  return context;
};
