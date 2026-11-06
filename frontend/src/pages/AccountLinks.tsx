import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Seal } from "../brand/Seal";
import { Sphere } from "../brand/Sphere";
import { api, ApiError } from "../lib/api";
import type { User } from "../lib/platformTypes";
import { useSession } from "../lib/session";

/** Páginas abertas pelos links dos e-mails: confirmar e-mail, redefinir senha e pedir o link. */

const message = (err: unknown) => (err instanceof ApiError ? err.message : "Não foi possível conectar. Tente de novo.");

function Shell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <main className="auth">
      <Sphere className="auth-sphere" />
      <Link to="/" className="brand-link auth-brand">
        <QuantumcoIcon size={40} />
        <span className="wordmark wordmark-lg">QUANTUMCO</span>
      </Link>
      <div className="auth-card glass-card">
        <div className="auth-card-head">
          <Seal size={72} />
        </div>
        <div className="auth-title">
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </div>
        {children}
      </div>
    </main>
  );
}

export function ConfirmEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { user, replaceUser } = useSession();
  const [state, setState] = useState<{ status: "wait" | "ok" | "error"; text: string; purpose?: string }>(() =>
    token ? { status: "wait", text: "" } : { status: "error", text: "Link incompleto. Abra de novo pelo e-mail." },
  );
  const sent = useRef(false);

  useEffect(() => {
    if (sent.current || !token) return; // o link vale uma vez: não reenviar no modo estrito do React
    sent.current = true;
    api<{ user: User; purpose: string }>("auth/confirm-email", { method: "POST", json: { token } })
      .then((body) => {
        setState({ status: "ok", text: body.user.email, purpose: body.purpose });
        if (user && user.id === body.user.id) replaceUser(body.user);
      })
      .catch((err: unknown) => setState({ status: "error", text: message(err) }));
  }, [token, user, replaceUser]);

  const changed = state.purpose === "change_email";
  return (
    <Shell
      title={state.status === "ok" ? (changed ? "E-mail alterado" : "E-mail confirmado") : state.status === "error" ? "Link inválido" : "Confirmando…"}
      subtitle={
        state.status === "ok"
          ? changed
            ? `A partir de agora, sua conta usa ${state.text}.`
            : `Obrigado! ${state.text} está confirmado.`
          : state.status === "error"
            ? state.text
            : "Só um instante."
      }
    >
      {state.status !== "wait" && (
        <Link to={user ? "/perfil" : "/entrar"} className="cta cta-block">
          {user ? "Ir para o perfil" : "Entrar"}
          <span className="cta-arrow" aria-hidden="true">
            →
          </span>
        </Link>
      )}
    </Shell>
  );
}

export function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const navigate = useNavigate();
  const { replaceUser } = useSession();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState(token ? "" : "Link incompleto. Peça um novo.");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password.length < 8) return setError("A senha precisa ter pelo menos 8 caracteres.");
    if (password !== confirm) return setError("As duas senhas não são iguais.");
    setBusy(true);
    setError("");
    try {
      const body = await api<{ user: User }>("auth/password/reset", { method: "POST", json: { token, new_password: password } });
      replaceUser(body.user);
      navigate("/perfil", { replace: true });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell title="Nova senha" subtitle="Escolha a nova senha. As outras sessões abertas serão encerradas.">
      <form onSubmit={submit} noValidate className="fields">
        <label className="input-field">
          <span className="label label-row">
            <span>NOVA SENHA</span>
            <span className="field-hint">mínimo de 8 caracteres</span>
          </span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" placeholder="••••••••••" />
        </label>
        <label className="input-field">
          <span className="label">REPITA A SENHA</span>
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" placeholder="••••••••••" />
        </label>
        {error && (
          <div className="form-error" role="alert">
            {error}
          </div>
        )}
        <button type="submit" className="cta cta-block" disabled={busy || !token}>
          {busy ? "Aguarde…" : "Salvar nova senha"}
          <span className="cta-arrow" aria-hidden="true">
            →
          </span>
        </button>
        <p className="switch">
          Link vencido? <Link to="/esqueci-senha">Pedir outro</Link>
        </p>
      </form>
    </Shell>
  );
}

export function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError("Informe um e-mail válido.");
    setBusy(true);
    setError("");
    try {
      await api("auth/password/forgot", { method: "POST", json: { email: email.trim() } });
      setSent(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Shell
      title="Esqueci a senha"
      subtitle={sent ? "Se houver uma conta com esse e-mail, o link chega em instantes. Ele vale por 1 hora." : "Enviamos um link para você criar uma senha nova."}
    >
      {sent ? (
        <Link to="/entrar" className="cta cta-block">
          Voltar para entrar
          <span className="cta-arrow" aria-hidden="true">
            →
          </span>
        </Link>
      ) : (
        <form onSubmit={submit} noValidate className="fields">
          <label className="input-field">
            <span className="label">E-MAIL</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="voce@instituicao.org" />
          </label>
          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="cta cta-block" disabled={busy}>
            {busy ? "Enviando…" : "Enviar link"}
            <span className="cta-arrow" aria-hidden="true">
              →
            </span>
          </button>
          <p className="switch">
            Lembrou? <Link to="/entrar">Entrar</Link>
          </p>
        </form>
      )}
    </Shell>
  );
}
