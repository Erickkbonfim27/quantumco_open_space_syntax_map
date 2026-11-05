import { Link, useNavigate } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Sphere } from "../brand/Sphere";
import { useSession } from "../lib/session";

const FEATURES = [
  ["01", "Sintaxe espacial", "Integração e escolha angulares, de 400 m até a cidade inteira."],
  ["02", "Cenários", "Salve versões da análise e volte a elas quando quiser."],
  ["03", "Polígonos", "Recorte áreas e leia as camadas em níveis."],
  ["04", "Dados abertos", "Malha do OpenStreetMap e metodologia versionada."],
] as const;

export function Landing() {
  const navigate = useNavigate();
  const { user } = useSession();
  return (
    <main className="landing">
      <Sphere className="landing-sphere" />
      <header className="topbar">
        <Link to="/" className="brand-link">
          <QuantumcoIcon size={40} />
          <span className="wordmark wordmark-lg">QUANTUMCO</span>
        </Link>
        <span className="spacer" />
        <Link to="/map" className="text-link">
          Ver o mapa de Brusque
        </Link>
        {user ? (
          <button type="button" className="pill pill-light topbar-cta" onClick={() => navigate("/painel")}>
            Meus cenários
          </button>
        ) : (
          <>
            <button type="button" className="pill pill-outline" onClick={() => navigate("/entrar")}>
              Entrar
            </button>
            <button type="button" className="pill pill-light topbar-cta" onClick={() => navigate("/criar-conta")}>
              Criar conta
            </button>
          </>
        )}
      </header>

      <section className="hero">
        <span className="kicker">QUÂNTICA · URBANISMO · CIDADES INTELIGENTES · IA</span>
        <h1>Ferramentas de pesquisa para ler e simular cidades.</h1>
        <p>
          Monte cenários, desenhe polígonos e compare medidas de sintaxe espacial sobre a malha do
          OpenStreetMap.
        </p>
        <div className="hero-actions">
          <button type="button" className="cta" onClick={() => navigate(user ? "/painel" : "/criar-conta")}>
            {user ? "Abrir meus cenários" : "Criar conta"}
            <span className="cta-arrow" aria-hidden="true">
              →
            </span>
          </button>
          <button type="button" className="pill pill-outline pill-lg" onClick={() => navigate("/map")}>
            Ver o mapa de Brusque
          </button>
          {!user && (
            <button type="button" className="pill pill-ghost pill-lg" onClick={() => navigate("/entrar")}>
              Já tenho conta
            </button>
          )}
        </div>
      </section>

      <section className="features" aria-label="O que você encontra">
        {FEATURES.map(([n, title, text]) => (
          <div key={n} className="feature">
            <span className="mono muted-2">{n}</span>
            <span className="feature-title">{title}</span>
            <span className="feature-text">{text}</span>
          </div>
        ))}
      </section>
    </main>
  );
}
