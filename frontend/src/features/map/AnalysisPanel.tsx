import type { AnalysisManifest, Measure, RadiusKey } from "../../lib/types";
import { RADII, SYNTAX_PALETTE } from "./syntaxPalette";

const MEASURES: { key: Measure; label: string }[] = [
  { key: "nain", label: "Integração" },
  { key: "nach", label: "Escolha" },
];

interface AnalysisPanelProps {
  analysis: AnalysisManifest | null;
  measure: Measure;
  radius: RadiusKey;
  onMeasure: (measure: Measure) => void;
  onRadius: (radius: RadiusKey) => void;
}

/** Medida, raio e escala de cor (design "Quantumco App"). */
export function AnalysisPanel({ analysis, measure, radius, onMeasure, onRadius }: AnalysisPanelProps) {
  const disabled = analysis === null;
  const isIntegration = measure === "nain";
  return (
    <section className="panel-section" aria-labelledby="analysis-title">
      <h2 id="analysis-title" className="sr-only">
        Análise sintática
      </h2>
      <div className="field">
        <span className="label">MEDIDA</span>
        <div className="segmented segmented-2" role="radiogroup" aria-label="Medida">
          {MEASURES.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={option.key === measure}
              disabled={disabled}
              onClick={() => onMeasure(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <span className="label">RAIO</span>
        <div className="segmented segmented-5 mono" role="radiogroup" aria-label="Raio">
          {RADII.map((option) => (
            <button
              key={option.key}
              type="button"
              role="radio"
              aria-checked={option.key === radius}
              disabled={disabled}
              onClick={() => onRadius(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div className="field">
        <div className="ramp" aria-hidden="true">
          {SYNTAX_PALETTE.map((color) => (
            <span key={color} style={{ background: color }} />
          ))}
        </div>
        <div className="ramp-labels">
          <span>{isIntegration ? "Menos integrado" : "Menos escolhido"}</span>
          <span>{isIntegration ? "Mais integrado" : "Mais escolhido"}</span>
        </div>
      </div>
      {analysis === null ? (
        <p className="notice">
          <span className="dot" aria-hidden="true" /> Análise sintática ainda não calculada. Rode{" "}
          <code>uv run quantumco analysis run</code>.
        </p>
      ) : (
        analysis.preliminary && (
          <p className="notice">
            <span className="dot dot-warn" aria-hidden="true" /> Preliminar: {analysis.engine}{" "}
            {analysis.engine_version}, validação contra o depthmapX pendente. Classes por
            percentil da extensão viária de Brusque.
          </p>
        )
      )}
      <ul className="legend">
        <li>
          <span className="swatch swatch-buffer" aria-hidden="true" />
          Entorno (faixa de 7 km, só para o cálculo)
        </li>
        <li>
          <span className="swatch swatch-outline" aria-hidden="true" />
          Limite de Brusque
        </li>
      </ul>
    </section>
  );
}
