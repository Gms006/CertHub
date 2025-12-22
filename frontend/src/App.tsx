import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import AppShell from "./components/AppShell";
import CertificatesPage from "./pages/Certificates";
import Login from "./pages/Login";
import ResetPassword from "./pages/ResetPassword";
import SetPassword from "./pages/SetPassword";

const App = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/set-password" element={<SetPassword />} />
        <Route path="/auth/reset-password" element={<ResetPassword />} />
        <Route element={<AppShell />}>
          <Route path="/certificados" element={<CertificatesPage />} />
          <Route path="/" element={<CertificatesPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
};

export default App;
