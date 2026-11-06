import { Link } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { useSession } from "../lib/session";
import { UserMenu } from "./UserMenu";

export type PlatformSection = "cenarios" | "dados" | "metodologia" | "perfil";

export function PlatformBar({ active }: { active: PlatformSection }) {
  const { user } = useSession();
  return (
    <header className="platform-bar">
      <Link to="/" className="brand-link">
        <QuantumcoIcon size={32} />
        <span className="wordmark">QUANTUMCO</span>
      </Link>
      <nav className="tabs" aria-label="Seções">
        {user && (
          <Link to="/painel" className={active === "cenarios" ? "tab tab-on" : "tab"}>
            Cenários
          </Link>
        )}
        <Link to="/map" className="tab">
          Mapa público
        </Link>
        <Link to="/dados" className={active === "dados" ? "tab tab-on" : "tab"}>
          Dados
        </Link>
        <Link to="/metodologia" className={active === "metodologia" ? "tab tab-on" : "tab"}>
          Metodologia
        </Link>
      </nav>
      <span className="spacer" />
      <Link to="/map" className="pill pill-outline pill-sm only-mobile">
        Mapa
      </Link>
      <UserMenu />
    </header>
  );
}
