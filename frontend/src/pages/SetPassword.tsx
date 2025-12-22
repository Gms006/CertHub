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
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto max-w-lg rounded-3xl border border-slate-200 bg-white p-8 shadow-soft">
        <h2 className="text-xl font-semibold text-slate-900">Primeiro acesso</h2>
        <p className="mt-2 text-sm text-slate-500">
          Informe o token enviado pelo admin para configurar sua senha inicial.
        </p>
        <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
          <label className="block text-xs font-semibold text-slate-500">
            Token 1x
            <input
              className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-700"
              type="text"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="Cole o token aqui"
              required
            />
          </label>
          <label className="block text-xs font-semibold text-slate-500">
            Nova senha
            <input
              className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-700"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              placeholder="Nova senha"
              required
            />
          </label>
          <button
            className="h-11 w-full rounded-2xl bg-[#0e2659] text-sm font-semibold text-white transition hover:bg-[#0e2659]/90"
            type="submit"
            disabled={loading}
          >
            {loading ? "Salvando..." : "Definir senha"}
          </button>
          {message && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
              {message}
            </div>
          )}
        </form>
      </div>
    </div>
  );
};

export default SetPassword;
