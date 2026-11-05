import type { Position } from "geojson";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { SYNTAX_PALETTE } from "../features/map/syntaxPalette";
import { medianClass } from "../features/workspace/geometry";
import { LayerStack } from "../features/workspace/LayerStack";
import { LoadingScreen } from "../features/workspace/LoadingScreen";
import { type MapFlags, PolygonMap, type PolygonMapHandle } from "../features/workspace/PolygonMap";
import { api, ApiError } from "../lib/api";
import type {
  PolygonCollection,
  PolygonStats,
  TerritoryProfile,
  Workspace,
} from "../lib/platformTypes";
import { useSession } from "../lib/session";
import type {
  AnalysisManifest,
  Manifest,
  Measure,
  MunicipalityCollection,
  NetworkCollection,
  SnapshotData,
} from "../lib/types";

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

const ICONS = {
  select: "M5 3l14 8-6 1.5L10 19z",
  draw: "M12 3l8 6-3 10H7L4 9z",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  fit: "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
  export: "M12 4v11 M7 10l5 5 5-5 M5 20h14",
} as const;

const STEPS = [
  "CARREGANDO O CENÁRIO",
  "CARREGANDO A MALHA DO OSM",
  "CARREGANDO INTEGRAÇÃO E ESCOLHA",
  "CALCULANDO AS CAMADAS DOS POLÍGONOS",
];

function download(name: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/geo+json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

export function WorkspaceMap() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useSession();
  const mapRef = useRef<PolygonMapHandle>(null);

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [data, setData] = useState<SnapshotData | null>(null);
  const [stats, setStats] = useState<Record<string, PolygonStats>>({});
  // perfil territorial: só do polígono aberto (é mais pesado), guardado por id
  const [profiles, setProfiles] = useState<Record<string, TerritoryProfile | "erro">>({});
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [measure, setMeasure] = useState<Measure>("nain");
  const [tool, setTool] = useState<"select" | "draw">("select");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [flags, setFlags] = useState<MapFlags>({ net: true, ent: true, lim: true, lab: true });
  const [query, setQuery] = useState("");
  const [draftVertices, setDraftVertices] = useState(0);
  const [cursor, setCursor] = useState<string>("—");
  const [saving, setSaving] = useState(false);

  const loadStats = useCallback(async (features: Workspace["features"]) => {
    const entries = await Promise.all(
      features.map(async (f) => {
        const result = await api<PolygonStats>("syntax/polygon-stats", {
          method: "POST",
          json: { coordinates: f.geometry.coordinates[0] },
        }).catch(() => null);
        return [f.properties.id, result] as const;
      }),
    );
    setStats((current) => {
      const next = { ...current };
      for (const [key, value] of entries) if (value) next[key] = value;
      return next;
    });
  }, []);

  useEffect(() => {
    const polygon = workspace?.features.find((f) => f.properties.id === selectedId);
    if (!polygon || profiles[polygon.properties.id]) return;
    const key = polygon.properties.id;
    api<TerritoryProfile>("territory/polygon-profile", {
      method: "POST",
      json: { coordinates: polygon.geometry.coordinates[0] },
    })
      .then((result) => setProfiles((current) => ({ ...current, [key]: result })))
      .catch(() => setProfiles((current) => ({ ...current, [key]: "erro" })));
  }, [selectedId, workspace, profiles]);

  // carga real, com progresso por etapa
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const ws = await api<Workspace>(`workspaces/${id}`);
        if (!alive) return;
        setWorkspace(ws);
        setMeasure(ws.measure);
        setStep(1);
        const [manifest, municipality] = await Promise.all([
          api<Manifest>("network/manifest"),
          api<MunicipalityCollection>("network/municipality"),
        ]);
        setStep(2);
        const [analysis, network] = await Promise.all([
          api<AnalysisManifest>("syntax/manifest"),
          api<NetworkCollection>("syntax/links"),
        ]);
        if (!alive) return;
        setStep(3);
        await loadStats(ws.features);
        if (!alive) return;
        setData({ manifest, municipality, network, analysis, scenario: null });
        setStep(4);
      } catch (err) {
        if (alive) setError(err instanceof ApiError ? err.message : String(err));
      }
    })();
    return () => {
      alive = false;
    };
  }, [id, loadStats]);

  const polygons: PolygonCollection = useMemo(
    () => ({ type: "FeatureCollection", features: workspace?.features ?? [] }),
    [workspace],
  );

  const refresh = async () => {
    const ws = await api<Workspace>(`workspaces/${id}`);
    setWorkspace(ws);
    return ws;
  };

  const onDrawComplete = async (ring: Position[]) => {
    setTool("select");
    setSaving(true);
    try {
      const created = await api<{ id: string }>(`workspaces/${id}/polygons`, {
        method: "POST",
        json: { coordinates: ring },
      });
      const ws = await refresh();
      await loadStats(ws.features.filter((f) => f.properties.id === created.id));
      setSelectedId(created.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  const removePolygon = async (polygonId: string) => {
    await api(`workspaces/${id}/polygons/${polygonId}`, { method: "DELETE" }).catch(() => undefined);
    if (selectedId === polygonId) setSelectedId(null);
    await refresh();
  };

  const changeMeasure = (m: Measure) => {
    setMeasure(m);
    void api(`workspaces/${id}`, { method: "PATCH", json: { measure: m } }).catch(() => undefined);
  };

  const exportFeatures = (only?: string) => {
    const features = polygons.features
      .filter((f) => !only || f.properties.id === only)
      .map((f) => {
        const profile = profiles[f.properties.id];
        const territory =
          profile && profile !== "erro"
            ? { ...profile, features: undefined } // sem a amostra de pontos (só para desenho)
            : null;
        return {
          ...f,
          properties: {
            ...f.properties,
            camadas: { ...(stats[f.properties.id] ?? {}), territorio: territory },
          },
        };
      });
    download("quantumco-poligonos.geojson", { type: "FeatureCollection", features });
  };

  if (error && !workspace) {
    return (
      <div className="center-message">
        <p>{error}</p>
        <Link to="/painel">← Voltar aos cenários</Link>
      </div>
    );
  }
  if (!workspace || !data) {
    return (
      <LoadingScreen
        name={workspace?.name ?? "Abrindo cenário"}
        progress={(step / STEPS.length) * 100}
        step={STEPS[Math.min(step, STEPS.length - 1)] ?? ""}
      />
    );
  }

  const selected = polygons.features.find((f) => f.properties.id === selectedId) ?? null;
  const q = query.trim().toLowerCase();
  const visible = polygons.features.filter(
    (f) => !q || `${f.properties.code} ${f.properties.name}`.toLowerCase().includes(q),
  );
  const all = polygons.features.map((f) => stats[f.properties.id]).filter(Boolean) as PolygonStats[];
  const sumArea = all.reduce((a, s) => a + s.territory.area_km2, 0);
  const sumLinks = all.reduce((a, s) => a + s.network.links, 0);
  const histo = SYNTAX_PALETTE.map((_, i) =>
    all.reduce((a, s) => a + (s.network.by_radius.n?.[`${measure}_classes_km`]?.[i] ?? 0), 0),
  );
  const histoMax = Math.max(1e-9, ...histo);
  const legendTitle = measure === "nain" ? "INTEGRAÇÃO (NAIN) · R n" : "ESCOLHA (NACH) · R n";

  const tools: { key: keyof typeof ICONS; title: string; on: boolean }[] = [
    { key: "select", title: "Selecionar", on: tool === "select" },
    { key: "draw", title: "Desenhar polígono", on: tool === "draw" },
    { key: "layers", title: "Malha sintática", on: flags.net },
    { key: "fit", title: "Enquadrar Brusque", on: false },
    { key: "export", title: "Exportar todos (GeoJSON)", on: false },
  ];

  function handleTool(key: keyof typeof ICONS) {
    if (key === "select") setTool("select");
    if (key === "draw") {
      setSelectedId(null);
      setTool("draw");
    }
    if (key === "layers") setFlags((f) => ({ ...f, net: !f.net }));
    if (key === "fit") mapRef.current?.fitAll();
    if (key === "export") exportFeatures();
  }

  return (
    <div className="ws">
      <header className="ws-bar">
        <button type="button" className="pill pill-outline pill-sm" onClick={() => navigate("/painel")}>
          ← Cenários
        </button>
        <QuantumcoIcon size={32} />
        <nav className="tabs" aria-label="Ferramentas">
          <Link to="/map" className="tab">
            Mapa sintático
          </Link>
          <span className="tab tab-on">Polígonos</span>
          <span className="tab tab-off" title="Em breve">
            Comparar
          </span>
          <span className="tab tab-off" title="Em breve">
            Relatórios
          </span>
        </nav>
        <span className="spacer" />
        <input
          className="search search-sm"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Buscar polígono"
          aria-label="Buscar polígono"
        />
        <div className="segmented segmented-2 ws-measure" role="radiogroup" aria-label="Medida">
          {(["nain", "nach"] as const).map((m) => (
            <button key={m} type="button" role="radio" aria-checked={measure === m} onClick={() => changeMeasure(m)}>
              {m === "nain" ? "Integração" : "Escolha"}
            </button>
          ))}
        </div>
        <span className="avatar" title={user?.name}>
          {user?.initials}
        </span>
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

      <aside className="ws-side">
        <div className="ws-cards">
          <div className="mini-card">
            <span className="muted small">Área analisada</span>
            <span className="mini-value">
              {fmt(sumArea, 2)}
              <span className="muted small"> km²</span>
            </span>
          </div>
          <div className="mini-card">
            <span className="muted small">Trechos</span>
            <span className="mini-value">{sumLinks.toLocaleString("pt-BR")}</span>
          </div>
          <div className="mini-card mini-wide">
            <div className="row-between muted small">
              <span>Distribuição nos polígonos</span>
              <span className="mono">R n</span>
            </div>
            <div className="histo" aria-hidden="true">
              {histo.map((v, i) => (
                <span
                  key={i}
                  style={{ height: `${Math.round((v / histoMax) * 100)}%`, background: SYNTAX_PALETTE[i] }}
                />
              ))}
            </div>
          </div>
        </div>

        <div className="row-between ws-list-head">
          <span className="label">POLÍGONOS ({polygons.features.length})</span>
          <button
            type="button"
            className="pill pill-green pill-sm"
            onClick={() => {
              setSelectedId(null);
              setTool("draw");
            }}
          >
            + Desenhar
          </button>
        </div>
        {tool === "draw" && (
          <div className="draw-hint">
            Clique para adicionar vértices. Feche clicando no primeiro ponto, com Enter ou com duplo
            clique. Esc cancela.
          </div>
        )}
        {saving && <div className="muted small ws-pad">Salvando polígono…</div>}
        {error && <div className="form-error ws-pad">{error}</div>}
        <ul className="poly-list">
          {visible.length === 0 && (
            <li className="muted small ws-pad">
              {polygons.features.length === 0 ? "Desenhe um polígono sobre o mapa para ler as camadas." : "Nenhum polígono encontrado."}
            </li>
          )}
          {visible.map((f) => {
            const s = stats[f.properties.id];
            const value = s?.network.by_radius.n?.[measure];
            const cls = medianClass(s?.network.by_radius.n?.[`${measure}_classes_km`]);
            const on = f.properties.id === selectedId;
            return (
              <li key={f.properties.id}>
                <button
                  type="button"
                  className={on ? "poly-item poly-item-on" : "poly-item"}
                  onClick={() => setSelectedId(on ? null : f.properties.id)}
                >
                  <span className="poly-dot" style={{ background: cls === null ? "#4A5155" : SYNTAX_PALETTE[cls] }} />
                  <span className="poly-text">
                    <span>{f.properties.name}</span>
                    <span className="mono muted-2 small">
                      {f.properties.code} · {s ? `${fmt(s.territory.area_km2, 2)} km²` : "…"}
                    </span>
                  </span>
                  <span className="mono soft small">{typeof value === "number" ? fmt(value, 2) : "–"}</span>
                </button>
                <button
                  type="button"
                  className="poly-del"
                  aria-label={`Remover ${f.properties.name}`}
                  onClick={() => void removePolygon(f.properties.id)}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>

        <div className="ws-section">
          <span className="label">CAMADAS DO MAPA</span>
          {(
            [
              ["net", "Malha sintática"],
              ["ent", "Entorno (faixa de 7 km)"],
              ["lim", "Limite de Brusque"],
              ["lab", "Rótulos dos polígonos"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="switch"
              aria-checked={flags[key]}
              className="toggle"
              onClick={() => setFlags((f) => ({ ...f, [key]: !f[key] }))}
            >
              <span className={flags[key] ? "toggle-track toggle-on" : "toggle-track"}>
                <span className="toggle-knob" />
              </span>
              {label}
            </button>
          ))}
        </div>

        <div className="ws-section">
          <span className="label">{legendTitle}</span>
          <div className="ramp" aria-hidden="true">
            {SYNTAX_PALETTE.map((c) => (
              <span key={c} style={{ background: c }} />
            ))}
          </div>
          <div className="row-between muted small">
            <span>Baixo</span>
            <span>Alto</span>
          </div>
        </div>
      </aside>

      <main className="ws-map">
        <PolygonMap
          ref={mapRef}
          data={data}
          polygons={polygons}
          measure={measure}
          flags={flags}
          tool={tool}
          selectedId={selectedId}
          rightInset={selected ? 740 : 0}
          onSelect={setSelectedId}
          onDrawComplete={(ring) => void onDrawComplete(ring)}
          onDrawCancel={() => setTool("select")}
          onDraftChange={setDraftVertices}
          onCursor={([lng, lat], zoom) => setCursor(`${fmt(lat, 5)}, ${fmt(lng, 5)} · zoom ${fmt(zoom, 1)}`)}
        />
        <div className="ws-overlay">
          <h1>{workspace.name}</h1>
          <div className="ws-chips">
            <span className="chip-dark">
              <span className="dot-green" aria-hidden="true" />
              {selected ? `${selected.properties.code} · ${selected.properties.name}` : `${polygons.features.length} polígonos ativos`}
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
        {selected && (
          <LayerStack
            key={selected.properties.id}
            polygon={selected}
            stats={stats[selected.properties.id]}
            profile={profiles[selected.properties.id]}
            measure={measure}
            network={data.network}
            onExport={() => exportFeatures(selected.properties.id)}
            onClose={() => setSelectedId(null)}
          />
        )}
      </main>

      <footer className="ws-status mono">
        <span className="row-gap">
          <span className="dot-green" aria-hidden="true" />
          MALHA v{data.manifest.methodology_version}
        </span>
        <span>{cursor}</span>
        <span>{tool === "draw" ? `DESENHANDO · ${draftVertices} VÉRTICES` : "SELECIONAR"}</span>
        <span className="spacer" />
        <span>© OpenStreetMap · OpenFreeMap · Desenvolvido por Erick K. Bonfim</span>
      </footer>
    </div>
  );
}
