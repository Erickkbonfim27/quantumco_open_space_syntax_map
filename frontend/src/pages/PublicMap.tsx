import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Footer } from "../components/Footer";
import { UserMenu } from "../components/UserMenu";
import { BasemapPicker, LayerToggles, MapTabs, MeasureSwitch, OPEN_LAYERS, RadiusSection } from "../features/map/MapPanels";
import { DEFAULT_FLAGS, type MapFlags, MapView, type MapViewHandle, type Selection } from "../features/map/MapView";
import { ScenarioPanel } from "../features/map/ScenarioPanel";
import { SelectionPanel } from "../features/map/SelectionPanel";
import { RADII } from "../features/map/syntaxPalette";
import { useBasemap } from "../features/map/useBasemap";
import { ReleaseInfo } from "../features/release/ReleaseInfo";
import { useSnapshotData } from "../features/release/useSnapshotData";
import { type AddressHit, pinFor, SearchBox } from "../features/search/AddressSearch";
import { LoadingScreen } from "../features/workspace/LoadingScreen";
import { type City, CitySelect, cityPath, preferredCity, saveCity, useCities } from "../lib/city";
import { useSession } from "../lib/session";
import type { Measure, RadiusKey } from "../lib/types";

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

const ICONS = {
  select: "M5 3l14 8-6 1.5L10 19z",
  draw: "M12 3l8 6-3 10H7L4 9z",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  fit: "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
} as const;

/** `/map/:uf/:cidade`: o mapa de UMA cidade (troca pelo seletor; cada uma é independente). */
export function PublicMap() {
  const { uf = "", slug = "" } = useParams();
  const cities = useCities();
  if (cities.status === "loading") {
    return <LoadingScreen name="" progress={20} step="CARREGANDO AS CIDADES" />;
  }
  if (cities.status === "error") {
    return (
      <div className="center-message">
        <p>Não foi possível carregar as cidades: {cities.message}</p>
        <Link to="/">← Voltar ao início</Link>
      </div>
    );
  }
  const city = cities.cities.find((c) => c.uf.toLowerCase() === uf.toLowerCase() && c.slug === slug);
  if (!city) {
    const other = preferredCity(cities.cities);
    return (
      <div className="center-message">
        <p>Essa cidade ainda não está no quantumco.</p>
        {other && <Link to={cityPath(other)}>Ver o mapa de {other.name} →</Link>}
      </div>
    );
  }
  // cada cidade monta um mapa novo: nada de uma passa para a outra
  return <CityMap key={city.ibge_code} city={city} cities={cities.cities} />;
}

function CityMap({ city, cities }: { city: City; cities: City[] }) {
  const state = useSnapshotData(city.ibge_code);
  const navigate = useNavigate();
  const { user } = useSession();
  const mapRef = useRef<MapViewHandle>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [measure, setMeasure] = useState<Measure>("nain");
  const [radius, setRadius] = useState<RadiusKey>("n");
  const [cursor, setCursor] = useState("—");
  const [overlayError, setOverlayError] = useState<string | null>(null);
  const [flags, setFlags] = useState<MapFlags>(DEFAULT_FLAGS);
  const [basemap, setBasemap] = useBasemap();
  const [pin, setPin] = useState<AddressHit | null>(null);
  const pinOnMap = useMemo(() => pinFor(pin), [pin]);

  useEffect(() => {
    saveCity(city.ibge_code); // a próxima visita a /map volta para esta cidade
    document.title = `QUANTUMCO · ${city.name}`;
  }, [city]);

  const data = state.status === "ready" ? state.data : null;

  // extensão de rua dentro do município (a faixa de entorno serve só ao cálculo)
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
    return <LoadingScreen name={city.name} progress={55} step="CARREGANDO A MALHA SINTÁTICA" />;
  }

  const radiusLabel = RADII.find((r) => r.key === radius)?.label ?? radius;
  const legendTitle = `${measure === "nain" ? "INTEGRAÇÃO (NAIN)" : "ESCOLHA (NACH)"} · R ${radiusLabel}`;
  const polygonsTo = user ? "/painel" : "/entrar";
  const toggle = (key: keyof MapFlags) => setFlags((f) => ({ ...f, [key]: !f[key] }));

  const tools: { key: keyof typeof ICONS; title: string; on: boolean }[] = [
    { key: "select", title: "Selecionar trecho", on: true },
    { key: "draw", title: "Desenhar polígono (nos seus cenários)", on: false },
    { key: "layers", title: "Malha sintática", on: flags.net },
    { key: "fit", title: `Enquadrar ${city.name}`, on: false },
  ];

  function handleTool(key: keyof typeof ICONS) {
    if (key === "layers") toggle("net");
    if (key === "draw") navigate(polygonsTo);
    if (key === "fit") mapRef.current?.fitAll();
  }

  return (
    <div className="ws ws-public">
      <header className="ws-bar">
        <Link to="/" className="ws-brand" aria-label="Início">
          <QuantumcoIcon size={32} />
        </Link>
        <MapTabs active="mapa" polygonsTo={polygonsTo} />
        <CitySelect cities={cities} value={city.ibge_code} label="Cidade do mapa" compact />
        <span className="spacer" />
        <SearchBox city={city} className="only-desktop" mode="endereco" onAddress={setPin} />
        <MeasureSwitch measure={measure} onMeasure={setMeasure} className="only-desktop" />
        <UserMenu compact />
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
        <div className="ws-mobile-measure only-mobile">
          <MeasureSwitch measure={measure} onMeasure={setMeasure} />
        </div>
        <div className="ws-cards">
          <div className="mini-card">
            <span className="muted small">Trechos</span>
            <span className="mini-value">{data.manifest.cleaning_report.links_kept.toLocaleString("pt-BR")}</span>
          </div>
          <div className="mini-card">
            <span className="muted small">Ruas em {city.name}</span>
            <span className="mini-value">
              {fmt(totalKm, 0)}
              <span className="muted small"> km</span>
            </span>
          </div>
          <div className="mini-card mini-wide">
            <div className="row-between muted small">
              <span>Recorte uma área da cidade</span>
              <span className="mono">N1–N7</span>
            </div>
            <span className="small soft">
              Desenhe polígonos e leia população, renda, entorno, equipamentos, risco e edificações
              junto da sintaxe espacial.
            </span>
            <Link to={polygonsTo} className="pill pill-green pill-sm ws-card-cta">
              {user ? "Abrir meus cenários" : "Criar conta grátis"}
            </Link>
          </div>
        </div>

        <RadiusSection measure={measure} radius={radius} onRadius={setRadius} />

        <div className="ws-embed">
          {data.scenario && <ScenarioPanel scenario={data.scenario} measure={measure} radius={radius} />}
          <SelectionPanel selection={selection} measure={measure} radius={radius} onClose={() => setSelection(null)} />
        </div>

        <BasemapPicker basemap={basemap} onBasemap={setBasemap} />
        <LayerToggles flags={flags} onToggle={toggle} error={overlayError} />

        <div className="ws-embed">
          <ReleaseInfo manifest={data.manifest} analysis={data.analysis} />
          <Footer />
        </div>
      </aside>

      <main className="ws-map">
        <MapView
          ref={mapRef}
          city={city.ibge_code}
          data={data}
          measure={measure}
          radius={radius}
          flags={flags}
          selectedId={selection?.properties.link_id ?? null}
          onSelect={setSelection}
          basemap={basemap}
          pin={pinOnMap}
          onCursor={([lng, lat], zoom) => setCursor(`${fmt(lat, 5)}, ${fmt(lng, 5)} · zoom ${fmt(zoom, 1)}`)}
          onOverlayError={(o) => setOverlayError(OPEN_LAYERS.find(([k]) => k === o)?.[1] ?? o)}
        />
        <div className="ws-overlay">
          <h1>{city.name}</h1>
        </div>
        <div className="ws-zoom">
          <button type="button" aria-label="Aproximar" onClick={() => mapRef.current?.zoomIn()}>
            +
          </button>
          <button type="button" aria-label={`Enquadrar ${city.name}`} onClick={() => mapRef.current?.fitAll()}>
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
        <span className="row-gap" title={`Metodologia v${data.manifest.methodology_version}`}>
          <span className="dot-green" aria-hidden="true" />
          QUANTUMCO v{__APP_VERSION__}
        </span>
        <span>{legendTitle}</span>
        <span>{cursor}</span>
        <span>{selection ? `TRECHO #${selection.properties.link_id}` : "SELECIONAR"}</span>
        <span className="spacer" />
        <span>© OpenStreetMap · Desenvolvido por Erick K. Bonfim</span>
      </footer>
    </div>
  );
}
