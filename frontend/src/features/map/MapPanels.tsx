import { Link } from "react-router";

import type { Measure, RadiusKey } from "../../lib/types";
import { BASEMAPS, type BasemapId } from "./basemapStyle";
import { type MapFlags, OVERLAY_COLOR, type Overlay } from "./MapView";
import { RADII, SYNTAX_PALETTE } from "./syntaxPalette";

/** Seções da lateral compartilhadas pelo mapa público e pelo mapa do cenário. */

/** Abas da barra superior, iguais nos dois mapas (no celular, rótulos curtos). */
export function MapTabs({ active, polygonsTo }: { active: "mapa" | "poligonos"; polygonsTo: string }) {
  return (
    <nav className="tabs ws-tabs" aria-label="Ferramentas">
      <Link to="/map" className={active === "mapa" ? "tab tab-on" : "tab"}>
        <span className="only-desktop">Mapa sintático</span>
        <span className="only-mobile">Mapa</span>
      </Link>
      <Link to={polygonsTo} className={active === "poligonos" ? "tab tab-on" : "tab"}>
        Polígonos
      </Link>
    </nav>
  );
}

export function MeasureSwitch({
  measure,
  onMeasure,
  className = "",
}: {
  measure: Measure;
  onMeasure: (m: Measure) => void;
  className?: string;
}) {
  return (
    <div className={`segmented segmented-2 ws-measure ${className}`} role="radiogroup" aria-label="Medida">
      {(["nain", "nach"] as const).map((m) => (
        <button key={m} type="button" role="radio" aria-checked={measure === m} onClick={() => onMeasure(m)}>
          {m === "nain" ? "Integração" : "Escolha"}
        </button>
      ))}
    </div>
  );
}

export function RadiusSection({
  measure,
  radius,
  onRadius,
}: {
  measure: Measure;
  radius: RadiusKey;
  onRadius: (r: RadiusKey) => void;
}) {
  const isIntegration = measure === "nain";
  return (
    <div className="ws-section ws-section-first">
      <span className="label">RAIO</span>
      <div className="segmented segmented-5 mono" role="radiogroup" aria-label="Raio">
        {RADII.map((option) => (
          <button
            key={option.key}
            type="button"
            role="radio"
            aria-checked={option.key === radius}
            onClick={() => onRadius(option.key)}
          >
            {option.label}
          </button>
        ))}
      </div>
      <div className="ramp" aria-hidden="true">
        {SYNTAX_PALETTE.map((c) => (
          <span key={c} style={{ background: c }} />
        ))}
      </div>
      <div className="row-between muted small">
        <span>{isIntegration ? "Menos integrado" : "Menos escolhido"}</span>
        <span>{isIntegration ? "Mais integrado" : "Mais escolhido"}</span>
      </div>
    </div>
  );
}

const BASE_LAYERS: [keyof MapFlags, string][] = [
  ["net", "Malha sintática"],
  ["ent", "Entorno (faixa de 7 km)"],
  ["lim", "Limite de Brusque"],
];
export const OPEN_LAYERS: [Overlay, string, string][] = [
  ["risco", "Áreas de risco", "SGB 2018–19"],
  ["inundacao", "Inundação (suscetib.)", "IPT/SGB 2013"],
  ["saude", "Saúde", "CNES"],
  ["escolas", "Escolas", "CNEFE 2022"],
  ["lugares", "Comércio e serviços", "Overture"],
];

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" role="switch" aria-checked={on} className="toggle" onClick={onClick}>
      <span className={on ? "toggle-track toggle-on" : "toggle-track"}>
        <span className="toggle-knob" />
      </span>
      {children}
    </button>
  );
}

/** Fundo do mapa: miniaturas clicáveis (o padrão segue o tema claro/escuro). */
export function BasemapPicker({ basemap, onBasemap }: { basemap: BasemapId; onBasemap: (id: BasemapId) => void }) {
  return (
    <div className="ws-section">
      <span className="label">FUNDO DO MAPA</span>
      <div className="basemap-grid" role="radiogroup" aria-label="Fundo do mapa">
        {BASEMAPS.map((b) => (
          <button
            key={b.id}
            type="button"
            role="radio"
            aria-checked={basemap === b.id}
            className={basemap === b.id ? "basemap-opt basemap-on" : "basemap-opt"}
            onClick={() => onBasemap(b.id)}
            title={b.hint}
            aria-label={`${b.label} (${b.hint})`}
          >
            <span className="basemap-swatch" style={{ background: b.swatch }} aria-hidden="true" />
            <span className="basemap-name">{b.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function LayerToggles({
  flags,
  onToggle,
  withPolygons = false,
  error,
}: {
  flags: MapFlags;
  onToggle: (key: keyof MapFlags) => void;
  withPolygons?: boolean;
  error?: string | null;
}) {
  const base: [keyof MapFlags, string][] = withPolygons
    ? [...BASE_LAYERS, ["lab", "Rótulos dos polígonos"]]
    : BASE_LAYERS;
  return (
    <div className="ws-section">
      <span className="label">CAMADAS DO MAPA</span>
      {base.map(([key, label]) => (
        <Toggle key={key} on={flags[key]} onClick={() => onToggle(key)}>
          {label}
        </Toggle>
      ))}
      <span className="label ws-sublabel">RELEVO</span>
      <Toggle on={flags.relevo} onClick={() => onToggle("relevo")}>
        Sombreamento do relevo
        <span className="mono muted-2 small toggle-source">SRTM</span>
      </Toggle>
      <Toggle on={flags.terrain3d} onClick={() => onToggle("terrain3d")}>
        Relevo 3D <span className="beta">beta</span>
        <span className="mono muted-2 small toggle-source">Ctrl + arrastar</span>
      </Toggle>
      <span className="label ws-sublabel">DADOS ABERTOS</span>
      {OPEN_LAYERS.map(([key, label, source]) => (
        <Toggle key={key} on={flags[key]} onClick={() => onToggle(key)}>
          <span className="toggle-swatch" style={{ background: OVERLAY_COLOR[key] }} aria-hidden="true" />
          {label}
          <span className="mono muted-2 small toggle-source">{source}</span>
        </Toggle>
      ))}
      <Toggle on={flags.predios} onClick={() => onToggle("predios")}>
        <span className="toggle-swatch toggle-swatch-ink" aria-hidden="true" />
        Edificações
        <span className="mono muted-2 small toggle-source">Overture · zoom 13+</span>
      </Toggle>
      {error && <div className="form-error">Não foi possível carregar a camada “{error}”.</div>}
    </div>
  );
}
