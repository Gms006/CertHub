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
    <div className="min-h-screen bg-slate-100 px-4 py-10">
      <div className="mx-auto max-w-lg rounded-3xl border border-slate-200 bg-white p-8 shadow-soft">
        <h2 className="text-xl font-semibold text-slate-900">Reset de senha</h2>
        <p className="mt-2 text-sm text-slate-500">
          {hasToken
            ? "Informe o token enviado por e-mail para atualizar sua senha."
            : "Informe seu e-mail corporativo para receber o link de reset."}
        </p>
        {hasToken ? (
          <form className="mt-6 space-y-4" onSubmit={handleConfirm}>
            <label className="block text-xs font-semibold text-slate-500">
              Token 1x
              <input
                className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-700"
                type="text"
                value={token}
                onChange={(event) => setToken(event.target.value)}
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
                required
              />
            </label>
            <button
              className="h-11 w-full rounded-2xl bg-[#0e2659] text-sm font-semibold text-white transition hover:bg-[#0e2659]/90"
              type="submit"
              disabled={loading}
            >
              {loading ? "Atualizando..." : "Atualizar senha"}
            </button>
          </form>
        ) : (
          <form className="mt-6 space-y-4" onSubmit={handleInit}>
            <label className="block text-xs font-semibold text-slate-500">
              Email
              <input
                className="mt-2 h-11 w-full rounded-2xl border border-slate-200 bg-white px-4 text-sm text-slate-700"
                type="email"
                placeholder="maria@netocontabilidade.com.br"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <button
              className="h-11 w-full rounded-2xl bg-[#0e2659] text-sm font-semibold text-white transition hover:bg-[#0e2659]/90"
              type="submit"
              disabled={loading}
            >
              {loading ? "Enviando..." : "Enviar link de reset"}
            </button>
          </form>
        )}
        {message && (
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600">
            {message}
          </div>
        )}
      </div>
    </div>
  );
};

export default ResetPassword;
