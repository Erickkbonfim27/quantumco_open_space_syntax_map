import { useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Footer } from "../components/Footer";
import {
  type MapFlags,
  MapView,
  type MapViewHandle,
  OVERLAY_COLOR,
  type Overlay,
  type Selection,
} from "../features/map/MapView";
import { ScenarioPanel } from "../features/map/ScenarioPanel";
import { SelectionPanel } from "../features/map/SelectionPanel";
import { RADII, SYNTAX_PALETTE } from "../features/map/syntaxPalette";
import { ReleaseInfo } from "../features/release/ReleaseInfo";
import { useSnapshotData } from "../features/release/useSnapshotData";
import { LoadingScreen } from "../features/workspace/LoadingScreen";
import { useSession } from "../lib/session";
import type { Measure, RadiusKey } from "../lib/types";

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

const ICONS = {
  select: "M5 3l14 8-6 1.5L10 19z",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  draw: "M12 3l8 6-3 10H7L4 9z",
  fit: "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
} as const;

const BASE_LAYERS: [keyof MapFlags, string][] = [
  ["net", "Malha sintática"],
  ["ent", "Entorno (faixa de 7 km)"],
  ["lim", "Limite de Brusque"],
];
const OPEN_LAYERS: [Overlay, string, string][] = [
  ["risco", "Áreas de risco", "SGB 2018–19"],
  ["inundacao", "Inundação (suscetib.)", "IPT/SGB 2013"],
  ["saude", "Saúde", "CNES"],
  ["escolas", "Escolas", "CNEFE 2022"],
];

export function PublicMap() {
  const state = useSnapshotData();
  const navigate = useNavigate();
  const { user } = useSession();
  const mapRef = useRef<MapViewHandle>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [measure, setMeasure] = useState<Measure>("nain");
  const [radius, setRadius] = useState<RadiusKey>("n");
  const [cursor, setCursor] = useState("—");
  const [overlayError, setOverlayError] = useState<string | null>(null);
  const [flags, setFlags] = useState<MapFlags>({
    net: true,
    ent: true,
    lim: true,
    inundacao: false,
    risco: false,
    saude: false,
    escolas: false,
  });

  const data = state.status === "ready" ? state.data : null;

  // extensão de rua em Brusque (a faixa de entorno serve só ao cálculo)
  const totalKm = useMemo(
    () =>
      (data?.network.features ?? []).reduce(
        (sum, f) => (f.properties.zone === "result" ? sum + f.properties.length_m / 1000 : sum),
        0,
      ),
    [data],
  );

  if (state.status === "error") {
    return (
      <div className="center-message">
        <p>Não foi possível carregar o mapa: {state.message}</p>
        <Link to="/">← Voltar ao início</Link>
      </div>
    );
  }
  if (!data) {
    return <LoadingScreen name="Brusque" progress={55} step="CARREGANDO A MALHA SINTÁTICA" />;
  }

  const radiusLabel = RADII.find((r) => r.key === radius)?.label ?? radius;
  const legendTitle = `${measure === "nain" ? "INTEGRAÇÃO (NAIN)" : "ESCOLHA (NACH)"} · R ${radiusLabel}`;
  const isIntegration = measure === "nain";
  const toggle = (key: keyof MapFlags) => setFlags((f) => ({ ...f, [key]: !f[key] }));
  const goPolygons = () => navigate(user ? "/painel" : "/entrar");

  const tools: { key: keyof typeof ICONS; title: string; on: boolean }[] = [
    { key: "select", title: "Selecionar trecho", on: true },
    { key: "layers", title: "Malha sintática", on: flags.net },
    { key: "draw", title: "Desenhar polígono (nos seus cenários)", on: false },
    { key: "fit", title: "Enquadrar Brusque", on: false },
  ];

  function handleTool(key: keyof typeof ICONS) {
    if (key === "layers") toggle("net");
    if (key === "draw") goPolygons();
    if (key === "fit") mapRef.current?.fitAll();
  }

  return (
    <div className="ws ws-public">
      <header className="ws-bar">
        <Link to="/" className="ws-brand" aria-label="Início">
          <QuantumcoIcon size={32} />
        </Link>
        <nav className="tabs" aria-label="Ferramentas">
          <span className="tab tab-on">Mapa sintático</span>
          <Link to={user ? "/painel" : "/entrar"} className="tab">
            Polígonos
          </Link>
          <span className="tab tab-off" title="Em breve">
            Comparar
          </span>
          <span className="tab tab-off" title="Em breve">
            Relatórios
          </span>
        </nav>
        <span className="spacer" />
        <div className="segmented segmented-2 ws-measure" role="radiogroup" aria-label="Medida">
          {(["nain", "nach"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={measure === m} onClick={() => setMeasure(m)}>
              {m === "nain" ? "Integração" : "Escolha"}
            </button>
          ))}
        </div>
        {user ? (
          <Link to="/painel" className="avatar" title={`${user.name} · seus cenários`}>
            {user.initials}
          </Link>
        ) : (
          <div className="ws-auth">
            <Link to="/entrar" className="pill pill-outline pill-sm">
              Entrar
            </Link>
            <Link to="/criar-conta" className="pill pill-green pill-sm">
              Criar conta
            </Link>
          </div>
        )}
      </header>

      <nav className="ws-rail" aria-label="Ferramentas do mapa">
        {tools.map((t) => (
          <button
            key={t.key}
            type="button"
            title={t.title}
            aria-label={t.title}
            aria-pressed={t.on}
            className={t.on ? (t.key === "layers" ? "rail-btn rail-btn-green" : "rail-btn rail-btn-on") : "rail-btn"}
            onClick={() => handleTool(t.key)}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round">
              <path d={ICONS[t.key]} />
            </svg>
          </button>
        ))}
      </nav>

      <aside className="ws-side" aria-label="Painel do mapa sintático">
        <div className="ws-cards">
          <div className="mini-card">
            <span className="muted small">Trechos</span>
            <span className="mini-value">{data.manifest.cleaning_report.links_kept.toLocaleString("pt-BR")}</span>
          </div>
          <div className="mini-card">
            <span className="muted small">Ruas em Brusque</span>
            <span className="mini-value">
              {fmt(totalKm, 0)}
              <span className="muted small"> km</span>
            </span>
          </div>
          <div className="mini-card mini-wide">
            <div className="row-between muted small">
              <span>Análise angular de segmentos</span>
              <span className="mono">{data.analysis?.engine ?? "—"}</span>
            </div>
            <span className="small soft">
              Integração (NAIN) e escolha (NACH) em 5 raios; cores por percentil da extensão de rua
              de Brusque (7 classes).
            </span>
          </div>
        </div>

        <div className="ws-section ws-section-first">
          <span className="label">RAIO</span>
          <div className="segmented segmented-5 mono" role="radiogroup" aria-label="Raio">
            {RADII.map((option) => (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={option.key === radius}
                onClick={() => setRadius(option.key)}
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

        <div className="ws-embed">
          {data.scenario && <ScenarioPanel scenario={data.scenario} measure={measure} radius={radius} />}
          <SelectionPanel
            selection={selection}
            measure={measure}
            radius={radius}
            onClose={() => setSelection(null)}
          />
        </div>

        <div className="ws-section">
          <span className="label">CAMADAS DO MAPA</span>
          {BASE_LAYERS.map(([key, label]) => (
            <button key={key} type="button" role="switch" aria-checked={flags[key]} className="toggle" onClick={() => toggle(key)}>
              <span className={flags[key] ? "toggle-track toggle-on" : "toggle-track"}>
                <span className="toggle-knob" />
              </span>
              {label}
            </button>
          ))}
          <span className="label ws-sublabel">DADOS ABERTOS</span>
          {OPEN_LAYERS.map(([key, label, source]) => (
            <button key={key} type="button" role="switch" aria-checked={flags[key]} className="toggle" onClick={() => toggle(key)}>
              <span className={flags[key] ? "toggle-track toggle-on" : "toggle-track"}>
                <span className="toggle-knob" />
              </span>
              <span className="toggle-swatch" style={{ background: OVERLAY_COLOR[key] }} aria-hidden="true" />
              {label}
              <span className="mono muted-2 small toggle-source">{source}</span>
            </button>
          ))}
          {overlayError && <div className="form-error">Não foi possível carregar a camada “{overlayError}”.</div>}
        </div>

        <div className="ws-embed">
          <ReleaseInfo manifest={data.manifest} analysis={data.analysis} />
          <Footer />
        </div>
      </aside>

      <main className="ws-map">
        <MapView
          ref={mapRef}
          data={data}
          measure={measure}
          radius={radius}
          flags={flags}
          selectedId={selection?.properties.link_id ?? null}
          onSelect={setSelection}
          onCursor={([lng, lat], zoom) => setCursor(`${fmt(lat, 5)}, ${fmt(lng, 5)} · zoom ${fmt(zoom, 1)}`)}
          onOverlayError={(o) => setOverlayError(OPEN_LAYERS.find(([k]) => k === o)?.[1] ?? o)}
        />
        <div className="ws-overlay">
          <h1>Brusque</h1>
          <div className="ws-chips">
            <span className="chip-dark">
              <span className="dot-green" aria-hidden="true" />
              Mapa sintático aberto · OpenStreetMap
            </span>
            <span className="chip-dark mono">{legendTitle}</span>
          </div>
        </div>
        <div className="ws-zoom">
          <button type="button" aria-label="Aproximar" onClick={() => mapRef.current?.zoomIn()}>
            +
          </button>
          <button type="button" aria-label="Enquadrar Brusque" onClick={() => mapRef.current?.fitAll()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <circle cx="12" cy="12" r="7" />
              <circle cx="12" cy="12" r="2" />
              <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
            </svg>
          </button>
          <button type="button" aria-label="Afastar" onClick={() => mapRef.current?.zoomOut()}>
            −
          </button>
        </div>
      </main>

      <footer className="ws-status mono">
        <span className="row-gap">
          <span className="dot-green" aria-hidden="true" />
          MALHA v{data.manifest.methodology_version}
        </span>
        <span>{cursor}</span>
        <span>{selection ? `TRECHO #${selection.properties.link_id}` : "SELECIONAR"}</span>
        <span className="spacer" />
        <span>© OpenStreetMap · OpenFreeMap · Desenvolvido por Erick K. Bonfim</span>
      </footer>
    </div>
  );
}
