import { FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const ResetPassword = () => {
  const { resetPasswordInit, resetPasswordConfirm, loading, message } = useAuth();
  const [params] = useSearchParams();
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(params.get("token") ?? "");
  const [newPassword, setNewPassword] = useState("");
  const hasToken = token.length > 0;

  const handleInit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await resetPasswordInit(email);
  };

  const handleConfirm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await resetPasswordConfirm(token, newPassword);
  };

  return (
    <section>
      <h2>Reset de senha</h2>
      {hasToken ? (
        <form className="form-grid" onSubmit={handleConfirm}>
          <label>
            Token 1x
            <input
              type="text"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              required
            />
          </label>
          <label>
            Nova senha
            <input
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Atualizando..." : "Atualizar senha"}
          </button>
        </form>
      ) : (
        <form className="form-grid" onSubmit={handleInit}>
          <label>
            Email
            <input
              type="email"
              placeholder="maria@netocontabilidade.com.br"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <button type="submit" disabled={loading}>
            {loading ? "Enviando..." : "Enviar link de reset"}
          </button>
        </form>
      )}
      {message && <div className="message">{message}</div>}
    </section>
  );
};

export default ResetPassword;
