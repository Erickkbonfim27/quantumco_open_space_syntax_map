import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { apiUrl } from "../lib/api";
import type { User } from "../lib/platformTypes";
import { useSession } from "../lib/session";
import { type ThemePreference, useTheme } from "../lib/theme";

/** Foto de perfil, ou as iniciais quando não há foto. */
export function Avatar({ user, size = 36 }: { user: User; size?: number }) {
  const [broken, setBroken] = useState(false);
  const style = { width: size, height: size, fontSize: Math.round(size * 0.36) };
  if (user.avatar_url && !broken) {
    return <img className="avatar avatar-img" src={apiUrl(user.avatar_url)} alt="" style={style} onError={() => setBroken(true)} />;
  }
  return (
    <span className="avatar" style={style} aria-hidden="true">
      {user.initials}
    </span>
  );
}

const THEMES: [ThemePreference, string][] = [
  ["system", "Sistema"],
  ["light", "Claro"],
  ["dark", "Escuro"],
];

/** Avatar clicável do topo: perfil, cenários, tema e sair. Sem sessão, mostra Entrar/Criar conta. */
export function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, logOut, savePreferences } = useSession();
  const { preference, setPreference } = useTheme();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const esc = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", esc);
    };
  }, [open]);

  if (!user) {
    return (
      <div className="ws-auth">
        <Link to="/entrar" className="pill pill-outline pill-sm">
          Entrar
        </Link>
        <Link to="/criar-conta" className="pill pill-green pill-sm only-desktop">
          Criar conta
        </Link>
      </div>
    );
  }

  const chooseTheme = (value: ThemePreference) => {
    setPreference(value);
    savePreferences({ theme: value });
  };

  return (
    <div className="user-menu" ref={box}>
      <button
        type="button"
        className="user-menu-button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Conta de ${user.name}`}
        onClick={() => setOpen((v) => !v)}
      >
        {!compact && (
          <span className="user-text only-desktop">
            <span>{user.name}</span>
            <span className="muted-2">{user.organization ?? user.email}</span>
          </span>
        )}
        <Avatar user={user} />
      </button>
      {open && (
        <div className="user-menu-pop" role="menu">
          <div className="user-menu-head">
            <Avatar user={user} size={44} />
            <span className="user-menu-who">
              <span>{user.name}</span>
              <span className="muted-2 small">{user.email}</span>
            </span>
          </div>
          <Link to="/perfil" role="menuitem" className="user-menu-item" onClick={() => setOpen(false)}>
            Meu perfil
          </Link>
          <Link to="/painel" role="menuitem" className="user-menu-item" onClick={() => setOpen(false)}>
            Meus cenários
          </Link>
          <div className="user-menu-theme">
            <span className="label">TEMA</span>
            <div className="segmented segmented-3" role="radiogroup" aria-label="Tema">
              {THEMES.map(([value, label]) => (
                <button key={value} type="button" role="radio" aria-checked={preference === value} onClick={() => chooseTheme(value)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            role="menuitem"
            className="user-menu-item user-menu-out"
            onClick={() => void logOut().then(() => navigate("/"))}
          >
            Sair
          </button>
        </div>
      )}
    </div>
  );
}
