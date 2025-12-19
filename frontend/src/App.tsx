import { BrowserRouter, Link, Route, Routes } from "react-router-dom";

import Login from "./pages/Login";
import ResetPassword from "./pages/ResetPassword";
import SetPassword from "./pages/SetPassword";

const App = () => {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <div className="card">
          <h1>CertHub</h1>
          <p className="helper">
            Skeleton do portal para autenticação (S2). Use as rotas abaixo
            para login, definição de senha e reset.
          </p>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/auth/set-password" element={<SetPassword />} />
            <Route path="/auth/reset-password" element={<ResetPassword />} />
            <Route path="*" element={<Login />} />
          </Routes>
          <nav className="nav-links">
            <Link to="/login">Login</Link>
            <Link to="/auth/set-password">Primeiro acesso</Link>
            <Link to="/auth/reset-password">Reset de senha</Link>
          </nav>
        </div>
      </div>
    </BrowserRouter>
  );
};

export default App;
