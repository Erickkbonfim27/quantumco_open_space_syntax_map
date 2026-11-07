import type { Position } from "geojson";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { QuantumcoIcon } from "../brand/QuantumcoIcon";
import { Footer } from "../components/Footer";
import { UserMenu } from "../components/UserMenu";
import { CameraStore } from "../features/map/cameraStore";
import { BasemapPicker, LayerToggles, MapTabs, MeasureSwitch, OPEN_LAYERS, RadiusSection } from "../features/map/MapPanels";
import {
  DEFAULT_FLAGS,
  type MapFlags,
  type MapTool,
  MapView,
  type MapViewHandle,
  type Selection,
} from "../features/map/MapView";
import { SelectionPanel } from "../features/map/SelectionPanel";
import { RADII, SYNTAX_PALETTE } from "../features/map/syntaxPalette";
import { useBasemap } from "../features/map/useBasemap";
import { ReleaseInfo } from "../features/release/ReleaseInfo";
import { EDIT_LABEL, type EditTool, replaceReroute, toggleLinkEdit } from "../features/scenarios/edits";
import { DeltaLegend, EditsSection, type ResultView, RunSection } from "../features/scenarios/NetworkPanel";
import { useScenarioRun } from "../features/scenarios/useScenarioRun";
import { type AddressHit, pinFor, SearchBox, type SearchMode } from "../features/search/AddressSearch";
import { medianClass } from "../features/workspace/geometry";
import { LayerStack } from "../features/workspace/LayerStack";
import { LoadingScreen } from "../features/workspace/LoadingScreen";
import { api, ApiError, apiCached } from "../lib/api";
import { cityApi } from "../lib/city";
import type {
  NetworkEdit,
  PolygonCollection,
  PolygonStats,
  TerritoryProfile,
  Workspace,
} from "../lib/platformTypes";
import type {
  AnalysisManifest,
  LinkProperties,
  Manifest,
  Measure,
  MunicipalityCollection,
  NetworkCollection,
  RadiusKey,
  ScenarioManifest,
  SnapshotData,
} from "../lib/types";

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

const ICONS = {
  select: "M5 3l14 8-6 1.5L10 19z",
  draw: "M12 3l8 6-3 10H7L4 9z",
  layers: "M12 3l9 5-9 5-9-5z M3 13l9 5 9-5",
  fit: "M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5",
} as const;

const STEPS = [
  "CARREGANDO O CENÁRIO",
  "CARREGANDO A MALHA DO OSM",
  "CARREGANDO INTEGRAÇÃO E ESCOLHA",
  "CALCULANDO AS CAMADAS DOS POLÍGONOS",
];

export function WorkspaceMap() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const mapRef = useRef<MapViewHandle>(null);
  // rotação e inclinação do mapa, para o painel de camadas acompanhar ("seguir mapa")
  const [camera] = useState(() => new CameraStore());

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
  const [flags, setFlags] = useState<MapFlags>(DEFAULT_FLAGS);
  const [radius, setRadius] = useState<RadiusKey>("n");
  const [link, setLink] = useState<Selection | null>(null);
  const [overlayError, setOverlayError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("endereco");
  const [pin, setPin] = useState<AddressHit | null>(null);
  const [draftVertices, setDraftVertices] = useState(0);
  const [cursor, setCursor] = useState<string>("—");
  const [saving, setSaving] = useState(false);
  // edição da rede ("e se…") e cálculo na fila
  const [panel, setPanel] = useState<"poligonos" | "rede">("poligonos");
  const [editTool, setEditTool] = useState<EditTool | null>(null);
  const [rerouteTarget, setRerouteTarget] = useState<string | null>(null);
  const [savingEdits, setSavingEdits] = useState(false);
  const [view, setView] = useState<ResultView>("atual");
  const [result, setResult] = useState<{ runId: string; manifest: ScenarioManifest; network: NetworkCollection } | null>(null);
  const runState = useScenarioRun(id);
  // cenário só com raios locais: ao mostrar o resultado, sai de um raio não calculado (vai para o
  // maior calculado). Chamado ao trocar a visualização, não num efeito.
  const computedRadii = runState.run?.status === "done" ? runState.run.radii : undefined;
  const showView = useCallback(
    (next: ResultView) => {
      setView(next);
      if (next !== "atual" && computedRadii?.length && !computedRadii.includes(radius)) {
        setRadius(computedRadii[computedRadii.length - 1] ?? radius);
      }
    },
    [computedRadii, radius],
  );
  const [basemap, setBasemap] = useBasemap();
  const editsRef = useRef<NetworkEdit[]>([]);
  const finishedLive = runState.finishedLive;

  useEffect(() => {
    editsRef.current = workspace?.edits ?? [];
  }, [workspace]);

  // resultado do último cálculo concluído (rede com valores e deltas)
  const doneRunId = runState.run?.status === "done" ? runState.run.id : null;
  useEffect(() => {
    if (!doneRunId || result?.runId === doneRunId) return;
    let alive = true;
    Promise.all([
      api<ScenarioManifest>(`workspaces/${id}/result/manifest`),
      api<NetworkCollection>(`workspaces/${id}/result/links`),
    ])
      .then(([manifest, network]) => {
        if (!alive) return;
        setResult({ runId: doneRunId, manifest, network });
        if (finishedLive) showView("diferenca"); // acabou agora, com a pessoa olhando
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [doneRunId, id, result, finishedLive, showView]);

  const loadStats = useCallback(async (city: string, features: Workspace["features"]) => {
    const entries = await Promise.all(
      features.map(async (f) => {
        const result = await api<PolygonStats>(cityApi(city, "syntax/polygon-stats"), {
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
    if (!workspace || !polygon || profiles[polygon.properties.id]) return;
    const key = polygon.properties.id;
    api<TerritoryProfile>(cityApi(workspace.ibge_code, "territory/polygon-profile"), {
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
        // tudo em paralelo; as estatísticas dos polígonos chegam depois, sem segurar o mapa
        const wsReq = api<Workspace>(`workspaces/${id}`).then((ws) => {
          if (alive) {
            setWorkspace(ws);
            setMeasure(ws.measure);
            setStep((n) => Math.max(n, 1));
          }
          return ws;
        });
        // a rede e a análise são as da cidade do cenário
        const baseReq = wsReq.then((ws) =>
          Promise.all([
            apiCached<Manifest>(cityApi(ws.ibge_code, "network/manifest")),
            apiCached<MunicipalityCollection>(cityApi(ws.ibge_code, "network/municipality")),
          ]).then((r) => (setStep((n) => Math.max(n, 2)), r)),
        );
        const syntaxReq = wsReq.then((ws) =>
          Promise.all([
            apiCached<AnalysisManifest>(cityApi(ws.ibge_code, "syntax/manifest")),
            apiCached<NetworkCollection>(cityApi(ws.ibge_code, "syntax/links")),
          ]).then((r) => (setStep((n) => Math.max(n, 3)), r)),
        );
        const [ws, [manifest, municipality], [analysis, network]] = await Promise.all([wsReq, baseReq, syntaxReq]);
        if (!alive) return;
        setData({ manifest, municipality, network, analysis, scenario: null });
        setStep(4);
        void loadStats(ws.ibge_code, ws.features);
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

  // o que o mapa mostra: rede atual ou o resultado do cenário (valores ou diferença)
  const showingResult = view !== "atual" && result !== null;
  const mapData: SnapshotData | null = useMemo(
    () => (data && showingResult && result ? { ...data, network: result.network, scenario: result.manifest } : data),
    [data, showingResult, result],
  );
  const pinOnMap = useMemo(() => pinFor(pin), [pin]);

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
      await loadStats(ws.ibge_code, ws.features.filter((f) => f.properties.id === created.id));
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

  /** Grava a lista de edições (otimista: a tela muda antes, e volta se a API recusar). */
  const saveEdits = async (update: (edits: NetworkEdit[]) => NetworkEdit[]) => {
    const before = editsRef.current;
    const next = update(before);
    editsRef.current = next;
    setWorkspace((ws) => (ws ? { ...ws, edits: next, edits_count: next.length } : ws));
    setSavingEdits(true);
    setError("");
    try {
      const ws = await api<Workspace>(`workspaces/${id}/edits`, { method: "PUT", json: { edits: next } });
      if (editsRef.current === next) setWorkspace(ws);
    } catch (err) {
      editsRef.current = before;
      setWorkspace((ws) => (ws ? { ...ws, edits: before, edits_count: before.length } : ws));
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSavingEdits(false);
    }
  };

  const chooseEditTool = (next: EditTool | null) => {
    setEditTool(next);
    setRerouteTarget(null);
    setTool("select");
    if (next) {
      setView("atual"); // edita-se sobre o mapa atual
      setSelectedId(null);
    }
  };

  const linkEdit = (type: "remove" | "close", props: LinkProperties) =>
    void saveEdits((edits) => toggleLinkEdit(edits, type, props));

  const onPickLink = (props: LinkProperties) => {
    if (!editTool || props.new) return;
    if (editTool === "remove" || editTool === "close") linkEdit(editTool, props);
    if (editTool === "reroute") setRerouteTarget(props.link_id);
  };

  const onLineComplete = (coords: Position[]) => {
    const line = coords.map(([x = 0, y = 0]) => [x, y] as [number, number]);
    if (editTool === "add") void saveEdits((edits) => [...edits, { type: "add", coords: line }]);
    if (editTool === "reroute" && rerouteTarget) {
      const target = rerouteTarget;
      void saveEdits((edits) => replaceReroute(edits, target, line));
      setRerouteTarget(null);
    }
  };

  const focusEdit = (edit: NetworkEdit) => {
    const geometry = edit.coords ?? data?.network.features.find((f) => f.properties.link_id === edit.link_id)?.geometry.coordinates;
    if (geometry) mapRef.current?.focus(geometry);
  };

  if (error && !workspace) {
    return (
      <div className="center-message">
        <p>{error}</p>
        <Link to="/painel">← Voltar aos cenários</Link>
      </div>
    );
  }
  if (!workspace || !data || !mapData) {
    return (
      <LoadingScreen
        name={workspace?.name ?? "Abrindo cenário"}
        progress={(step / STEPS.length) * 100}
        step={STEPS[Math.min(step, STEPS.length - 1)] ?? ""}
      />
    );
  }

  const cityName = workspace.city.split(",")[0] ?? workspace.city;
  const selected = polygons.features.find((f) => f.properties.id === selectedId) ?? null;
  const q = query.trim().toLowerCase();
  const visible = polygons.features.filter(
    (f) => !q || `${f.properties.code} ${f.properties.name}`.toLowerCase().includes(q),
  );
  const all = polygons.features.map((f) => stats[f.properties.id]).filter(Boolean) as PolygonStats[];
  const sumArea = all.reduce((a, s) => a + s.territory.area_km2, 0);
  const sumLinks = all.reduce((a, s) => a + s.network.links, 0);
  const radiusLabel = RADII.find((r) => r.key === radius)?.label ?? radius;
  const histo = SYNTAX_PALETTE.map((_, i) =>
    all.reduce((a, s) => a + (s.network.by_radius[radius]?.[`${measure}_classes_km`]?.[i] ?? 0), 0),
  );
  const histoMax = Math.max(1e-9, ...histo);
  const legendTitle = `${measure === "nain" ? "INTEGRAÇÃO (NAIN)" : "ESCOLHA (NACH)"} · R ${radiusLabel}`;
  const toggle = (key: keyof MapFlags) => setFlags((f) => ({ ...f, [key]: !f[key] }));
  const editing = panel === "rede" && editTool !== null;
  const mapTool: MapTool = editing
    ? editTool === "add" || (editTool === "reroute" && rerouteTarget)
      ? "line"
      : "pick"
    : tool;
  const mapEdits = showingResult ? runState.run?.edit_list : workspace.edits;
  const linkActions =
    panel === "rede" && link && !showingResult && !link.properties.new ? (
      <div className="edit-actions">
        <button type="button" className="pill pill-outline pill-sm" onClick={() => linkEdit("remove", link.properties)}>
          Remover
        </button>
        <button type="button" className="pill pill-outline pill-sm" onClick={() => linkEdit("close", link.properties)}>
          Interditar
        </button>
        <button
          type="button"
          className="pill pill-outline pill-sm"
          onClick={() => {
            chooseEditTool("reroute");
            setRerouteTarget(link.properties.link_id);
          }}
        >
          Redesenhar
        </button>
      </div>
    ) : null;

  const tools: { key: keyof typeof ICONS; title: string; on: boolean }[] = [
    { key: "select", title: "Selecionar", on: tool === "select" },
    { key: "draw", title: "Desenhar polígono", on: tool === "draw" },
    { key: "layers", title: "Malha sintática", on: flags.net },
    { key: "fit", title: `Enquadrar ${cityName}`, on: false },
  ];

  function handleTool(key: keyof typeof ICONS) {
    if (key === "select") {
      setTool("select");
      setEditTool(null);
    }
    if (key === "draw") {
      setSelectedId(null);
      setPanel("poligonos");
      setEditTool(null);
      setTool("draw");
    }
    if (key === "layers") toggle("net");
    if (key === "fit") mapRef.current?.fitAll();
  }

  return (
    <div className="ws">
      <header className="ws-bar">
        <button type="button" className="pill pill-outline pill-sm" onClick={() => navigate("/painel")} aria-label="Voltar aos cenários">
          ←<span className="only-desktop">&nbsp;Cenários</span>
        </button>
        <span className="only-desktop ws-brand">
          <QuantumcoIcon size={32} />
        </span>
        <MapTabs active="poligonos" polygonsTo={`/painel/cenario/${id}`} />
        <span className="spacer" />
        <SearchBox
          city={{ ibge_code: workspace.ibge_code, name: cityName }}
          className="only-desktop"
          modes={["endereco", "poligono"]}
          mode={searchMode}
          onMode={(m) => {
            setSearchMode(m);
            if (m === "endereco") setQuery("");
            else setPin(null);
          }}
          polygonQuery={query}
          onPolygonQuery={(text) => {
            setQuery(text);
            setPanel("poligonos");
          }}
          onAddress={setPin}
        />
        <MeasureSwitch measure={measure} onMeasure={changeMeasure} className="only-desktop" />
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

      <aside className="ws-side">
        <div className="ws-mobile-measure only-mobile">
          <MeasureSwitch measure={measure} onMeasure={changeMeasure} />
        </div>
        <div className="segmented segmented-2 ws-panel-tabs" role="tablist" aria-label="O que editar">
          {(
            [
              ["poligonos", `Polígonos (${polygons.features.length})`],
              ["rede", `Rede (${workspace.edits.length})`],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={panel === key}
              aria-checked={panel === key}
              onClick={() => {
                setPanel(key);
                if (key === "poligonos") setEditTool(null);
                else setTool("select");
              }}
            >
              {label}
            </button>
          ))}
        </div>
        {panel === "rede" ? (
          <>
            <EditsSection
              edits={workspace.edits}
              tool={editTool}
              rerouteTarget={rerouteTarget}
              draftVertices={draftVertices}
              saving={savingEdits}
              network={mapData.network}
              onTool={chooseEditTool}
              onRemoveEdit={(index) => void saveEdits((edits) => edits.filter((_, i) => i !== index))}
              onClear={() => void saveEdits(() => [])}
              onFocusEdit={focusEdit}
            />
            {error && <div className="form-error ws-pad">{error}</div>}
            <RunSection
              edits={workspace.edits}
              run={runState.run}
              offset={runState.offset}
              busy={runState.busy}
              error={runState.error}
              measure={measure}
              radius={radius}
              view={view}
              resultReady={result !== null && result.runId === doneRunId}
              onRequest={(radii) => {
                chooseEditTool(null);
                void runState.request(radii);
              }}
              onCancel={() => void runState.cancel()}
              onView={showView}
            />
            {showingResult && view === "diferenca" && <DeltaLegend />}
          </>
        ) : (
        <>
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
              <span className="mono">R {radiusLabel}</span>
            </div>
            <div className="histo" aria-hidden="true">
              {histo.map((v, i) => (
                <span key={i} style={{ height: `${Math.round((v / histoMax) * 100)}%`, background: SYNTAX_PALETTE[i] }} />
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
            const value = s?.network.by_radius[radius]?.[measure];
            const cls = medianClass(s?.network.by_radius[radius]?.[`${measure}_classes_km`]);
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

        </>
        )}

        <RadiusSection measure={measure} radius={radius} onRadius={setRadius} />

        <div className="ws-embed">
          <SelectionPanel selection={link} measure={measure} radius={radius} onClose={() => setLink(null)} actions={linkActions} />
        </div>

        <BasemapPicker basemap={basemap} onBasemap={setBasemap} />
        <LayerToggles flags={flags} onToggle={toggle} withPolygons withListings error={overlayError} />

        <div className="ws-embed">
          <ReleaseInfo manifest={data.manifest} analysis={data.analysis} />
          <Footer />
        </div>
      </aside>

      <main className="ws-map">
        <MapView
          ref={mapRef}
          city={workspace.ibge_code}
          camera={camera}
          data={mapData}
          measure={measure}
          radius={radius}
          flags={flags}
          selectedId={rerouteTarget ?? link?.properties.link_id ?? null}
          onSelect={setLink}
          basemap={basemap}
          symbology={view === "cenario" ? "syntax" : "delta"}
          edits={mapEdits}
          showNewLines={!showingResult}
          onPickLink={onPickLink}
          onLineComplete={onLineComplete}
          pin={pinOnMap}
          polygons={polygons}
          selectedPolygonId={selectedId}
          onSelectPolygon={setSelectedId}
          tool={mapTool}
          rightInset={selected ? 740 : 0}
          onDrawComplete={(ring) => void onDrawComplete(ring)}
          onDrawCancel={() => {
            if (rerouteTarget) setRerouteTarget(null);
            else if (editTool) setEditTool(null);
            else setTool("select");
          }}
          onDraftChange={setDraftVertices}
          onCursor={([lng, lat], zoom) => setCursor(`${fmt(lat, 5)}, ${fmt(lng, 5)} · zoom ${fmt(zoom, 1)}`)}
          onOverlayError={(o) =>
            setOverlayError(o === "imoveis" ? "Imóveis à venda" : (OPEN_LAYERS.find(([k]) => k === o)?.[1] ?? o))
          }
        />
        <div className="ws-overlay">
          <h1>{workspace.name}</h1>
          <div className="ws-chips">
            <span className="chip-dark">
              <span className="dot-green" aria-hidden="true" />
              {selected ? `${selected.properties.code} · ${selected.properties.name}` : `${polygons.features.length} polígonos ativos`}
            </span>
            {workspace.edits.length > 0 && (
              <span className="chip-dark">
                <span className="dot-orange" aria-hidden="true" />
                {workspace.edits.length} {workspace.edits.length === 1 ? "edição" : "edições"} na rede
              </span>
            )}

          </div>
        </div>
        <div className="ws-zoom">
          <button type="button" aria-label="Aproximar" onClick={() => mapRef.current?.zoomIn()}>
            +
          </button>
          <button type="button" aria-label={`Enquadrar ${cityName}`} onClick={() => mapRef.current?.fitAll()}>
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
            radius={radius}
            network={data.network}
            camera={camera}
            onClose={() => setSelectedId(null)}
          />
        )}
      </main>

      <footer className="ws-status mono">
        <span className="row-gap" title={`Metodologia v${data.manifest.methodology_version}`}>
          <span className="dot-green" aria-hidden="true" />
          QUANTUMCO v{__APP_VERSION__}
        </span>
        <span title="A cidade é escolhida ao criar o cenário e não muda">{workspace.city.toUpperCase()}</span>
        <span>
          {showingResult ? `CENÁRIO · ${view === "cenario" ? "VALORES" : "DIFERENÇA"} · ` : ""}
          {legendTitle}
        </span>
        <span>{cursor}</span>
        <span>
          {editing
            ? `REDE · ${EDIT_LABEL[editTool].verb.toUpperCase()}${draftVertices ? ` · ${draftVertices} PONTOS` : ""}`
            : tool === "draw"
              ? `DESENHANDO · ${draftVertices} VÉRTICES`
              : link
                ? `TRECHO #${link.properties.link_id}`
                : "SELECIONAR"}
        </span>
        <span className="spacer" />
        <span>© OpenStreetMap · Desenvolvido por Erick K. Bonfim</span>
      </footer>
    </div>
  );
}
