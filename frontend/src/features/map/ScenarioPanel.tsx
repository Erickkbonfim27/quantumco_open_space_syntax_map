import type { Measure, RadiusKey, ScenarioManifest } from "../../lib/types";
import { DELTA_COLORS, MEASURE_LABEL, RADII } from "./syntaxPalette";

interface ScenarioPanelProps {
  scenario: ScenarioManifest;
  measure: Measure;
  radius: RadiusKey;
}

const km = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });

const LEGEND: [string, string][] = [
  [DELTA_COLORS.gainStrong, "ganhou 2+ classes"],
  [DELTA_COLORS.gain, "ganhou 1 classe"],
  [DELTA_COLORS.same, "sem mudança"],
  [DELTA_COLORS.loss, "perdeu 1 classe"],
  [DELTA_COLORS.lossStrong, "perdeu 2+ classes"],
  [DELTA_COLORS.removed, "trecho removido"],
  [DELTA_COLORS.added, "rua nova"],
];

/** Cenário "e se…": resumo e legenda das mudanças em relação ao mapa publicado. */
export function ScenarioPanel({ scenario, measure, radius }: ScenarioPanelProps) {
  const change = scenario.summary_result_zone[`${measure}_${radius}`];
  const radiusLabel = RADII.find((r) => r.key === radius)?.label ?? radius;
  return (
    <section className="panel-section" aria-labelledby="scenario-title">
      <div className="card">
        <span className="label">CENÁRIO</span>
        <span id="scenario-title" className="scenario-name">
          {scenario.name}
        </span>
        <span className="muted">
          {scenario.removed.length} trecho(s) removido(s) · {scenario.added.length} rua(s) nova(s) ·
          comparado ao mapa publicado
        </span>
        {change ? (
          <div className="stats">
            <div>
              <span className="stat-value delta-up">+{km.format(change.km_up)}</span>
              <span className="stat-label">km subiram de classe</span>
            </div>
            <div>
              <span className="stat-value delta-down">−{km.format(change.km_down)}</span>
              <span className="stat-label">km caíram de classe</span>
            </div>
          </div>
        ) : (
          <span className="muted">Resumo calculado para n e 800 m.</span>
        )}
        <span className="muted">
          {MEASURE_LABEL[measure]} · R {radiusLabel}
        </span>
        <ul className="legend">
          {LEGEND.map(([color, label]) => (
            <li key={label}>
              <span className="swatch" style={{ height: 3, background: color }} aria-hidden="true" />
              {label}
            </li>
          ))}
        </ul>
        <a className="button-ghost" href="/">
          ← Voltar ao mapa publicado
        </a>
      </div>
    </section>
  );
}
