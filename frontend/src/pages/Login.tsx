import { FormEvent, useState } from "react";

import { useAuth } from "../hooks/useAuth";

const Login = () => {
  const { login, loading, message } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await login(email, password);
  };

  return (
    <section>
      <h2>Entrar</h2>
      <form className="form-grid" onSubmit={handleSubmit}>
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
        <label>
          Senha
          <input
            type="password"
            placeholder="Senha segura"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>
        {message && <div className="message">{message}</div>}
      </form>
    </section>
  );
};

export default Login;
