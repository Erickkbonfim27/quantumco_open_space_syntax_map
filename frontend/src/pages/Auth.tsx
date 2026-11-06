import { type FormEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Seal } from "../brand/Seal";
import { Sphere } from "../brand/Sphere";
import { ApiError } from "../lib/api";
import { useSession } from "../lib/session";

const EMPTY = { name: "", organization: "", email: "", password: "" };

export function Auth({ mode }: { mode: "login" | "signup" }) {
  const navigate = useNavigate();
  const { user, loading, logIn, signUp } = useSession();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const signup = mode === "signup";

  if (!loading && user) return <Navigate to="/painel" replace />;

  const field = (key: keyof typeof EMPTY) => (value: string) => {
    setForm((f) => ({ ...f, [key]: value }));
    setError("");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const email = form.email.trim();
    if (signup && !form.name.trim()) return setError("Informe seu nome.");
    if (!/^\S+@\S+\.\S+$/.test(email)) return setError("Informe um e-mail válido.");
    if (signup && form.password.length < 8)
      return setError("A senha precisa ter pelo menos 8 caracteres.");
    if (!form.password) return setError("Informe sua senha.");
    setBusy(true);
    try {
      if (signup) await signUp({ ...form, email });
      else await logIn(email, form.password);
      navigate("/painel");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Não foi possível conectar. Tente de novo.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <Sphere className="auth-sphere" />
      <Link to="/" className="brand-link auth-brand">
        <QuantumcoIcon size={40} />
        <span className="wordmark wordmark-lg">QUANTUMCO</span>
      </Link>
      <blockquote className="auth-quote">
        <p>Omnia quae realia vocamus ex rebus constant quae ut realia haberi non possunt</p>
        <footer>
          <span className="rule" aria-hidden="true" />
          Niels Bohr
        </footer>
      </blockquote>

      <form className="auth-card glass-card" onSubmit={submit} noValidate>
        <div className="auth-card-head">
          <Seal size={72} />
          <div className="segmented segmented-2 auth-tabs" role="tablist">
            <button type="button" role="tab" aria-checked={!signup} onClick={() => navigate("/entrar")}>
              Entrar
            </button>
            <button type="button" role="tab" aria-checked={signup} onClick={() => navigate("/criar-conta")}>
              Criar conta
            </button>
          </div>
        </div>
        <div className="auth-title">
          <h1>{signup ? "Criar conta" : "Acesse o laboratório"}</h1>
          <p>{signup ? "Seus cenários ficam salvos na sua conta." : "Entre para ver seus cenários."}</p>
        </div>
        <div className="fields">
          {signup && (
            <>
              <label className="input-field">
                <span className="label">NOME</span>
                <input
                  value={form.name}
                  onChange={(e) => field("name")(e.target.value)}
                  placeholder="Seu nome"
                  autoComplete="name"
                />
              </label>
              <label className="input-field">
                <span className="label">
                  INSTITUIÇÃO <span className="muted-2">(OPCIONAL)</span>
                </span>
                <input
                  value={form.organization}
                  onChange={(e) => field("organization")(e.target.value)}
                  placeholder="Universidade, prefeitura, escritório"
                  autoComplete="organization"
                />
              </label>
            </>
          )}
          <label className="input-field">
            <span className="label">E-MAIL</span>
            <input
              type="email"
              value={form.email}
              onChange={(e) => field("email")(e.target.value)}
              placeholder="voce@instituicao.org"
              autoComplete="email"
            />
          </label>
          <label className="input-field">
            <span className="label label-row">
              <span>SENHA</span>
              {signup ? (
                <span className="field-hint">mínimo de 8 caracteres</span>
              ) : (
                <Link to="/esqueci-senha" className="field-hint">
                  esqueci a senha
                </Link>
              )}
            </span>
            <input
              type="password"
              value={form.password}
              onChange={(e) => field("password")(e.target.value)}
              placeholder="••••••••••"
              autoComplete={signup ? "new-password" : "current-password"}
            />
          </label>
        </div>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <button type="submit" className="cta cta-block" disabled={busy}>
          {busy ? "Aguarde…" : signup ? "Criar conta" : "Entrar"}
          <span className="cta-arrow" aria-hidden="true">
            →
          </span>
        </button>
        <p className="switch">
          {signup ? "Já tem conta?" : "Ainda não tem conta?"}{" "}
          <Link to={signup ? "/entrar" : "/criar-conta"}>{signup ? "Entrar" : "Criar conta"}</Link>
        </p>
      </form>
    </main>
  );
}
