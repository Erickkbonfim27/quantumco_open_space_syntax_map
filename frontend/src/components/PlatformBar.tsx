import { Link, useNavigate } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { useSession } from "../lib/session";

const REPO = "https://github.com/Erickkbonfim27/quantumco_open_space_syntax_map/blob/main";

export function PlatformBar({ active }: { active: "cenarios" }) {
  const navigate = useNavigate();
  const { user, logOut } = useSession();
  return (
    <header className="platform-bar">
      <Link to="/" className="brand-link">
        <QuantumcoIcon size={32} />
        <span className="wordmark">QUANTUMCO</span>
      </Link>
      <nav className="tabs" aria-label="Seções">
        <Link to="/painel" className={active === "cenarios" ? "tab tab-on" : "tab"}>
          Cenários
        </Link>
        <Link to="/map" className="tab">
          Mapa público
        </Link>
        <a className="tab" href={`${REPO}/docs/data-sources.md`} target="_blank" rel="noreferrer">
          Dados
        </a>
        <a className="tab" href={`${REPO}/docs/decisions.md`} target="_blank" rel="noreferrer">
          Metodologia
        </a>
      </nav>
      <span className="spacer" />
      {user && (
        <div className="user-chip">
          <span className="user-text">
            <span>{user.name}</span>
            <span className="muted-2">{user.organization ?? user.email}</span>
          </span>
          <span className="avatar">{user.initials}</span>
        </div>
      )}
      <button
        type="button"
        className="pill pill-outline pill-sm"
        onClick={() => void logOut().then(() => navigate("/"))}
      >
        Sair
      </button>
    </header>
  );
}
