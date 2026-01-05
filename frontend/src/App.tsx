import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import ProtectedRoute from "./components/ProtectedRoute";
import { PreferencesProvider } from "./hooks/usePreferences";
import CertificatesPage from "./pages/Certificates";
import DevicesPage from "./pages/Devices";
import JobsPage from "./pages/Jobs";
import Login from "./pages/Login";
import AuditPage from "./pages/Audit";
import ResetPassword from "./pages/ResetPassword";
import SetPassword from "./pages/SetPassword";

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/set-password" element={<SetPassword />} />
        <Route path="/auth/reset-password" element={<ResetPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route
          element={
            <ProtectedRoute>
              <PreferencesProvider>
                <AppShell />
              </PreferencesProvider>
            </ProtectedRoute>
          }
        >
          <Route path="/certificados" element={<CertificatesPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/dispositivos" element={<DevicesPage />} />
          <Route path="/auditoria" element={<AuditPage />} />
          <Route path="/" element={<CertificatesPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
