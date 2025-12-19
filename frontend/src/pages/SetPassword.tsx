import { FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";

const SetPassword = () => {
  const { setPassword, loading, message } = useAuth();
  const [params] = useSearchParams();
  const [token, setToken] = useState(params.get("token") ?? "");
  const [newPassword, setNewPassword] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await setPassword(token, newPassword);
  };

  return (
    <section>
      <h2>Primeiro acesso</h2>
      <p className="helper">
        Informe o token enviado pelo admin para configurar sua senha inicial.
      </p>
      <form className="form-grid" onSubmit={handleSubmit}>
        <label>
          Token 1x
          <input
            type="text"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            placeholder="Cole o token aqui"
            required
          />
        </label>
        <label>
          Nova senha
          <input
            type="password"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
            placeholder="Nova senha"
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Salvando..." : "Definir senha"}
        </button>
        {message && <div className="message">{message}</div>}
      </form>
    </section>
  );
};

export default SetPassword;
