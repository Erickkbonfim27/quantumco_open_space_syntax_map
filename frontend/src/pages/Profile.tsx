import { type FormEvent, useRef, useState } from "react";

import { Footer } from "../components/Footer";
import { PlatformBar } from "../components/PlatformBar";
import { Avatar } from "../components/UserMenu";
import { BasemapPicker } from "../features/map/MapPanels";
import { useBasemap } from "../features/map/useBasemap";
import { api, ApiError } from "../lib/api";
import { squareAvatar } from "../lib/avatarImage";
import type { User } from "../lib/platformTypes";
import { useSession } from "../lib/session";
import { type ThemePreference, useTheme } from "../lib/theme";
import "./profile.css";

const since = new Intl.DateTimeFormat("pt-BR", { day: "numeric", month: "long", year: "numeric" });
const message = (err: unknown) => (err instanceof ApiError ? err.message : "Não foi possível conectar. Tente de novo.");

type Notice = { kind: "ok" | "error"; text: string } | null;

function NoticeLine({ notice }: { notice: Notice }) {
  if (!notice) return null;
  return (
    <div className={notice.kind === "ok" ? "pf-ok" : "form-error"} role={notice.kind === "ok" ? "status" : "alert"}>
      {notice.text}
    </div>
  );
}

/** Perfil: foto, dados, e-mail (com confirmação), senha (por link no e-mail) e preferências. */
export function Profile() {
  const { user, replaceUser, savePreferences } = useSession();
  const { preference, setPreference } = useTheme();
  const [basemap, setBasemap] = useBasemap();
  if (!user) return null;

  const accept = (body: { user: User }) => replaceUser(body.user);

  return (
    <div className="pf-page">
      <PlatformBar active="perfil" />
      <main className="pf-main">
        <header className="pf-head">
          <span className="label">MEU PERFIL</span>
          <h1>{user.name}</h1>
          <p className="muted">
            {user.organization ? `${user.organization} · ` : ""}
            {user.created_at ? `na quantumco desde ${since.format(new Date(user.created_at))}` : ""}
          </p>
        </header>

        <div className="pf-grid">
          <PhotoCard user={user} onUser={replaceUser} />
          <DataCard user={user} onUser={accept} />
          <EmailCard user={user} onUser={accept} />
          <PasswordCard user={user} />
          <section className="pf-card" aria-labelledby="pf-prefs">
            <h2 id="pf-prefs">Preferências</h2>
            <div className="pf-field">
              <span className="label">TEMA DA INTERFACE</span>
              <div className="segmented segmented-3" role="radiogroup" aria-label="Tema">
                {(
                  [
                    ["system", "Sistema"],
                    ["light", "Claro"],
                    ["dark", "Escuro"],
                  ] as [ThemePreference, string][]
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={preference === value}
                    onClick={() => {
                      setPreference(value);
                      savePreferences({ theme: value });
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="pf-embed">
              <BasemapPicker basemap={basemap} onBasemap={setBasemap} />
            </div>
            <p className="muted-2 small">Tema e fundo ficam salvos na sua conta e valem em qualquer aparelho.</p>
          </section>
        </div>
      </main>
      <Footer />
    </div>
  );
}

function PhotoCard({ user, onUser }: { user: User; onUser: (user: User) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const upload = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setNotice(null);
    try {
      const blob = await squareAvatar(file);
      const body = await api<{ user: User }>("me/avatar", { method: "PUT", body: blob, headers: { "Content-Type": blob.type } });
      onUser(body.user);
      setNotice({ kind: "ok", text: "Foto atualizada." });
    } catch (err) {
      setNotice({ kind: "error", text: err instanceof Error && !(err instanceof ApiError) ? err.message : message(err) });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  };

  const remove = async () => {
    setBusy(true);
    setNotice(null);
    try {
      onUser((await api<{ user: User }>("me/avatar", { method: "DELETE" })).user);
    } catch (err) {
      setNotice({ kind: "error", text: message(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="pf-card pf-photo" aria-labelledby="pf-photo">
      <h2 id="pf-photo">Foto</h2>
      <div className="pf-photo-row">
        <Avatar user={user} size={96} />
        <div className="pf-photo-actions">
          <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={(e) => void upload(e.target.files?.[0])} />
          <button type="button" className="pill pill-green pill-sm" disabled={busy} onClick={() => input.current?.click()}>
            {busy ? "Enviando…" : user.avatar_url ? "Trocar foto" : "Enviar foto"}
          </button>
          {user.avatar_url && (
            <button type="button" className="pill pill-outline pill-sm" disabled={busy} onClick={() => void remove()}>
              Remover
            </button>
          )}
          <span className="muted-2 small">PNG, JPEG ou WebP. Recortamos em quadrado (256 px).</span>
        </div>
      </div>
      <NoticeLine notice={notice} />
    </section>
  );
}

function DataCard({ user, onUser }: { user: User; onUser: (body: { user: User }) => void }) {
  const [name, setName] = useState(user.name);
  const [organization, setOrganization] = useState(user.organization ?? "");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const changed = name.trim() !== user.name || organization.trim() !== (user.organization ?? "");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setNotice({ kind: "error", text: "Informe seu nome." });
    setBusy(true);
    setNotice(null);
    try {
      onUser(await api<{ user: User }>("me", { method: "PATCH", json: { name, organization } }));
      setNotice({ kind: "ok", text: "Dados salvos." });
    } catch (err) {
      setNotice({ kind: "error", text: message(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="pf-card" onSubmit={submit} aria-labelledby="pf-data">
      <h2 id="pf-data">Dados</h2>
      <label className="input-field">
        <span className="label">NOME</span>
        <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={120} />
      </label>
      <label className="input-field">
        <span className="label">
          INSTITUIÇÃO <span className="muted-2">(OPCIONAL)</span>
        </span>
        <input value={organization} onChange={(e) => setOrganization(e.target.value)} placeholder="Universidade, prefeitura, escritório" autoComplete="organization" maxLength={160} />
      </label>
      <NoticeLine notice={notice} />
      <div>
        <button type="submit" className="pill pill-green pill-sm" disabled={busy || !changed}>
          {busy ? "Salvando…" : "Salvar"}
        </button>
      </div>
    </form>
  );
}

function EmailCard({ user, onUser }: { user: User; onUser: (body: { user: User }) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setNotice(null);
    try {
      await fn();
    } catch (err) {
      setNotice({ kind: "error", text: message(err) });
    } finally {
      setBusy(false);
    }
  };

  const change = (event: FormEvent) => {
    event.preventDefault();
    void run(async () => {
      const body = await api<{ user: User; sent_to: string }>("me/email", { method: "POST", json: { email: email.trim(), password } });
      onUser(body);
      setEditing(false);
      setEmail("");
      setPassword("");
      setNotice({ kind: "ok", text: `Enviamos um link para ${body.sent_to}. O e-mail só muda depois que você clicar nele.` });
    });
  };

  return (
    <section className="pf-card" aria-labelledby="pf-email">
      <h2 id="pf-email">E-mail</h2>
      <div className="pf-email-row">
        <span className="pf-email">{user.email}</span>
        <span className={user.email_verified ? "pf-badge pf-badge-ok" : "pf-badge pf-badge-warn"}>
          {user.email_verified ? "confirmado" : "não confirmado"}
        </span>
      </div>
      {!user.email_verified && (
        <button
          type="button"
          className="link-btn small pf-left"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const body = await api<{ sent_to: string }>("me/verification", { method: "POST" });
              setNotice({ kind: "ok", text: `Link de confirmação reenviado para ${body.sent_to}.` });
            })
          }
        >
          Reenviar link de confirmação
        </button>
      )}
      {user.pending_email && (
        <div className="pf-pending small">
          Aguardando confirmação de <strong>{user.pending_email}</strong>.{" "}
          <button type="button" className="link-btn small" disabled={busy} onClick={() => void run(async () => onUser(await api<{ user: User }>("me/email/pending", { method: "DELETE" })))}>
            Cancelar troca
          </button>
        </div>
      )}
      {editing ? (
        <form className="pf-inline-form" onSubmit={change}>
          <label className="input-field">
            <span className="label">NOVO E-MAIL</span>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" placeholder="voce@instituicao.org" required />
          </label>
          <label className="input-field">
            <span className="label">SENHA ATUAL</span>
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
          </label>
          <div className="row-gap">
            <button type="submit" className="pill pill-green pill-sm" disabled={busy || !email.trim() || !password}>
              {busy ? "Enviando…" : "Enviar link de confirmação"}
            </button>
            <button type="button" className="pill pill-outline pill-sm" onClick={() => setEditing(false)}>
              Cancelar
            </button>
          </div>
        </form>
      ) : (
        <div>
          <button type="button" className="pill pill-outline pill-sm" onClick={() => setEditing(true)}>
            Trocar e-mail
          </button>
        </div>
      )}
      <NoticeLine notice={notice} />
    </section>
  );
}

function PasswordCard({ user }: { user: User }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const send = async () => {
    setBusy(true);
    setNotice(null);
    try {
      const body = await api<{ sent_to: string }>("me/password", { method: "POST" });
      setNotice({ kind: "ok", text: `Enviamos o link para ${body.sent_to}. Ele vale por 1 hora.` });
    } catch (err) {
      setNotice({ kind: "error", text: message(err) });
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="pf-card" aria-labelledby="pf-password">
      <h2 id="pf-password">Senha</h2>
      <p className="muted small pf-text">
        Por segurança, a troca de senha é feita por um link enviado para <strong>{user.email}</strong>. Ao
        trocar, as outras sessões abertas (outros aparelhos) são encerradas.
      </p>
      <div>
        <button type="button" className="pill pill-outline pill-sm" disabled={busy} onClick={() => void send()}>
          {busy ? "Enviando…" : "Enviar link para trocar a senha"}
        </button>
      </div>
      <NoticeLine notice={notice} />
    </section>
  );
}
