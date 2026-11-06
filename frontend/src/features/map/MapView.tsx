import "maplibre-gl/dist/maplibre-gl.css";

import type { Feature, FeatureCollection, LineString, Polygon, Position } from "geojson";
import {
  type ExpressionSpecification,
  type FilterSpecification,
  type GeoJSONSource,
  Map as MapLibreMap,
  type MapMouseEvent,
  Marker,
  Popup,
  ScaleControl,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { config } from "../../config";
import { api } from "../../lib/api";
import { boundsOf } from "../../lib/geo";
import type { NetworkEdit, PolygonCollection } from "../../lib/platformTypes";
import { useTheme } from "../../lib/theme";
import type { LinkProperties, Measure, RadiusKey, SnapshotData } from "../../lib/types";
import { applyBasemap, type BasemapId, basemapStyle, LABEL_LAYER, type Tone, toneOf } from "./basemapStyle";
import { lineColor, lineOpacity, lineWidth } from "./highwayGroups";
import {
  deltaColor,
  deltaSortKey,
  deltaWidth,
  syntaxColor,
  syntaxSortKey,
  syntaxWidth,
} from "./syntaxPalette";

/**
 * O mapa da plataforma, igual no mapa público e no cenário: rede sintática (medida e raio),
 * camadas de dados abertos, clique em trecho e, quando há `polygons`, desenho e seleção de áreas.
 */

/** Entorno (sem classe) em cinza neutro, como no design. */
const BUFFER_GRAY = "#4A5155";
/** Passo da grade de pontos do fundo (px), igual ao design e ao CSS. */
const GRID = 36;
/** Distância (px) do primeiro vértice que fecha o polígono. */
const CLOSE_PX = 12;
/** Encaixe da via desenhada na rede (px na tela): segmento e, com prioridade, vértice. */
const SNAP_PX = 14;
const SNAP_VERTEX_PX = 9;

/** Cores das edições da rede (fora da escala sintática). */
export const EDIT_COLORS = {
  remove: "#FF5A5F",
  close: "#FFA53B",
  add: "#2BD46B",
  reroute: "#2BD46B",
} as const;

/** Cores "de tinta" por tom do fundo (limite, seleção, polígonos, rótulos). */
const INK: Record<Tone, { ink: string; halo: string; outline: string; poly: string; glow: number }> = {
  dark: { ink: "#F4F6F5", halo: "rgba(10,13,14,.92)", outline: "rgba(244,246,245,.5)", poly: "rgba(244,246,245,.7)", glow: 0.18 },
  light: { ink: "#0F1213", halo: "rgba(255,255,255,.94)", outline: "rgba(15,18,19,.55)", poly: "rgba(15,18,19,.7)", glow: 0.14 },
};

// O MapLibre 6 resolve o worker por uma URL dinâmica que o Vite não enxerga; registramos o
// arquivo explicitamente (ele é autocontido, sem imports).
setWorkerUrl(workerUrl);

const NETWORK = "network";
const MUNICIPALITY = "municipality";
const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

/** Camadas territoriais (dados abertos) baixadas sob demanda. */
export const OVERLAYS = ["inundacao", "risco", "saude", "escolas"] as const;
export type Overlay = (typeof OVERLAYS)[number];
const OVERLAY_ENDPOINT: Record<Overlay, string> = {
  inundacao: "territory/map/suscet_inundacao",
  risco: "territory/map/risco",
  saude: "territory/map/saude",
  escolas: "territory/map/escolas",
};
// Fora da paleta sintática, para não confundir com NAIN/NACH.
export const OVERLAY_COLOR: Record<Overlay, string> = {
  inundacao: "#3B8CFF",
  risco: "#FF6B5E",
  saude: "#2BD46B",
  escolas: "#F4F6F5",
};

// Relevo: Terrain Tiles da AWS (Mapzen; SRTM, USGS, ETOPO1), dados abertos, codificação terrarium.
const DEM_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const DEM_ATTRIBUTION =
  '<a href="https://registry.opendata.aws/terrain-tiles/" target="_blank" rel="noreferrer">Terrain Tiles (AWS · SRTM/USGS)</a>';
const TERRAIN_EXAGGERATION = 1.15;
const TERRAIN_PITCH = 50;

export interface MapFlags {
  relevo: boolean;
  terrain3d: boolean;
  net: boolean;
  ent: boolean;
  lim: boolean;
  lab: boolean;
  inundacao: boolean;
  risco: boolean;
  saude: boolean;
  escolas: boolean;
}

export const DEFAULT_FLAGS: MapFlags = {
  relevo: false,
  terrain3d: false,
  net: true,
  ent: true,
  lim: true,
  lab: true,
  inundacao: false,
  risco: false,
  saude: false,
  escolas: false,
};

export interface Selection {
  properties: LinkProperties;
  lngLat: [number, number];
}

export interface MapViewHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitAll: () => void;
  /** enquadra uma linha (ex.: uma edição da lista) */
  focus: (coords: Position[]) => void;
}

export type MapTool = "select" | "draw" | "line" | "pick";

interface MapViewProps {
  data: SnapshotData;
  measure: Measure;
  radius: RadiusKey;
  flags: MapFlags;
  selectedId: string | null;
  onSelect: (selection: Selection | null) => void;
  basemap?: BasemapId;
  /** cenário calculado: valores (escala sintática) ou diferença; padrão: diferença */
  symbology?: "syntax" | "delta";
  // edições da rede (cenário "e se…")
  edits?: NetworkEdit[];
  showNewLines?: boolean;
  onPickLink?: (link: LinkProperties) => void;
  onLineComplete?: (coords: Position[]) => void;
  /** endereço encontrado na busca: pin + enquadramento */
  pin?: { lngLat: [number, number]; label: string } | null;
  onCursor?: (lngLat: [number, number], zoom: number) => void;
  onOverlayError?: (overlay: Overlay) => void;
  // polígonos (cenário do usuário)
  polygons?: PolygonCollection;
  selectedPolygonId?: string | null;
  onSelectPolygon?: (id: string | null) => void;
  tool?: MapTool;
  rightInset?: number; // painel aberto à direita (enquadramento do polígono)
  onDrawComplete?: (ring: Position[]) => void;
  onDrawCancel?: () => void;
  onDraftChange?: (vertices: number) => void;
}

const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function popupHtml(overlay: Overlay, props: Record<string, unknown>): string {
  const str = (key: string) => escapeHtml(String(props[key] ?? ""));
  if (overlay === "risco") {
    const people = props.pessoas ? ` · ~${str("pessoas")} pessoas` : "";
    return `<strong>Risco ${str("categoria").toLowerCase()}</strong><br>${str("processo")}${people}<br><span>${str("local")} · SGB ${str("data").slice(0, 4)}</span>`;
  }
  if (overlay === "saude") {
    const sus = props.sus ? " · atende SUS" : "";
    return `<strong>${str("nome")}</strong><br><span>${str("tipo").replace(/_/g, " ")}${sus} · CNES</span>`;
  }
  if (overlay === "escolas") return `<strong>${str("nome")}</strong><br><span>Escola · CNEFE 2022</span>`;
  return `<strong>Suscetibilidade ${str("categoria").toLowerCase()} a inundação</strong><br><span>IPT/SGB 2013</span>`;
}

const NO_LINK: FilterSpecification = ["==", ["get", "link_id"], ""];

/** Ponto mais próximo de p no segmento ab (coordenadas de tela). */
function nearestOnSegment(p: { x: number; y: number }, a: { x: number; y: number }, b: { x: number; y: number }) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = dx * dx + dy * dy;
  const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len));
  return { x: a.x + t * dx, y: a.y + t * dy };
}

function lineParts(geometry: GeoJSON.Geometry): Position[][] {
  if (geometry.type === "LineString") return [geometry.coordinates];
  if (geometry.type === "MultiLineString") return geometry.coordinates;
  return [];
}

function editLines(edits: NetworkEdit[] | undefined): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (edits ?? [])
      .map((e, index) => ({ e, index }))
      .filter(({ e }) => e.coords && e.coords.length >= 2)
      .map(({ e, index }) => ({
        type: "Feature",
        properties: { kind: e.type, index },
        geometry: { type: "LineString", coordinates: e.coords as Position[] },
      })),
  };
}

const idsOf = (edits: NetworkEdit[] | undefined, ...types: NetworkEdit["type"][]) =>
  (edits ?? []).filter((e) => types.includes(e.type) && e.link_id).map((e) => e.link_id as string);

export const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(props, handleRef) {
  const { data, measure, radius, flags, selectedId, basemap = "auto", symbology = "delta" } = props;
  const { polygons, selectedPolygonId = null, tool = "select", rightInset = 0 } = props;
  const { edits, showNewLines = true, pin = null } = props;
  const { theme } = useTheme();
  const tone = toneOf(basemap, theme);
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const live = useRef(props);
  const loaded = useRef(new Set<Overlay>());
  const draft = useRef<Position[]>([]);
  const snapped = useRef<boolean[]>([]);
  const cursor = useRef<Position | null>(null);
  const fitted = useRef(false);
  const marker = useRef<Marker | null>(null);

  useEffect(() => {
    live.current = props;
  });

  const fitAll = () => {
    const instance = map.current;
    const bounds = boundsOf(data.municipality.features.map((f) => f.geometry));
    if (!instance || !bounds) return;
    const mobile = window.matchMedia("(max-width: 900px)").matches;
    const padding = mobile ? 24 : { top: 120, right: 48, bottom: 48, left: 48 };
    instance.fitBounds(bounds, { padding, duration: 0 });
  };

  useImperativeHandle(handleRef, () => ({
    zoomIn: () => map.current?.zoomIn(),
    zoomOut: () => map.current?.zoomOut(),
    fitAll,
    focus: (coords: Position[]) => {
      const bounds = boundsOf([{ type: "LineString", coordinates: coords }]);
      if (bounds) map.current?.fitBounds(bounds, { padding: 120, maxZoom: 17, duration: 600 });
    },
  }));

  const renderDraft = () => {
    const source = map.current?.getSource("draft") as GeoJSONSource | undefined;
    if (!source) return;
    const pts = draft.current;
    const line = live.current.tool === "line";
    const features: Feature[] = pts.map((p, i) => ({
      type: "Feature",
      properties: { first: !line && i === 0, snapped: line ? Boolean(snapped.current[i]) : null },
      geometry: { type: "Point", coordinates: p },
    }));
    const path = cursor.current ? [...pts, cursor.current] : pts;
    if (path.length >= 2) {
      features.push({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: path } as LineString });
    }
    const start = path[0];
    if (!line && path.length >= 3 && start) {
      features.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...path, start]] } as Polygon });
    }
    source.setData({ type: "FeatureCollection", features });
  };

  const clearDraft = () => {
    draft.current = [];
    snapped.current = [];
    cursor.current = null;
    renderDraft();
    live.current.onDraftChange?.(0);
  };

  const completeDraft = () => {
    const pts = draft.current;
    const start = pts[0];
    if (live.current.tool === "line") {
      if (pts.length < 2) return;
      clearDraft();
      live.current.onLineComplete?.(pts);
      return;
    }
    if (pts.length < 3 || !start) return;
    clearDraft();
    live.current.onDrawComplete?.([...pts, start]);
  };

  /** Encaixa um clique na rede (ou numa via nova já desenhada), em pixels de tela. */
  const snapToNetwork = (instance: MapLibreMap, x: number, y: number): { at: Position; snapped: boolean } => {
    const layers = ["links-hit", "edit-new"].filter((id) => instance.getLayer(id));
    const hits = instance.queryRenderedFeatures(
      [
        [x - SNAP_PX, y - SNAP_PX],
        [x + SNAP_PX, y + SNAP_PX],
      ],
      { layers },
    );
    const p = { x, y };
    let best: { x: number; y: number } | null = null;
    let bestD = Infinity;
    let vertex: { x: number; y: number } | null = null;
    let vertexD = Infinity;
    for (const hit of hits) {
      for (const part of lineParts(hit.geometry)) {
        const screen = part.map((c) => instance.project(c as [number, number]));
        screen.forEach((v, i) => {
          const d = Math.hypot(v.x - x, v.y - y);
          // pontas de trecho (cruzamentos) têm prioridade sobre o meio da linha
          const end = i === 0 || i === screen.length - 1;
          if (end && d < vertexD) [vertex, vertexD] = [v, d];
          const next = screen[i + 1];
          if (!next) return;
          const q = nearestOnSegment(p, v, next);
          const dq = Math.hypot(q.x - x, q.y - y);
          if (dq < bestD) [best, bestD] = [q, dq];
        });
      }
    }
    const chosen = vertex && vertexD <= SNAP_VERTEX_PX ? vertex : best && bestD <= SNAP_PX ? best : null;
    if (!chosen) return { at: instance.unproject([x, y]).toArray(), snapped: false };
    return { at: instance.unproject([(chosen as { x: number }).x, (chosen as { y: number }).y]).toArray(), snapped: true };
  };

  // cria o mapa uma vez
  useEffect(() => {
    if (!container.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: config.basemapStyleUrl ?? basemapStyle,
      center: [-48.917, -27.098],
      zoom: 12,
      attributionControl: { compact: false },
    });
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");

    // grade de pontos do design: o fundo (CSS) acompanha o arraste do mapa
    const anchor: [number, number] = [-48.917, -27.098];
    const syncGrid = () => {
      const el = container.current;
      if (!el) return;
      const p = instance.project(anchor);
      el.style.backgroundPosition = `${p.x % GRID}px ${p.y % GRID}px`;
    };
    instance.on("move", syncGrid);

    instance.on("load", () => {
      syncGrid();
      // a rede entra ANTES dos nomes de lugares, que ficam legíveis por cima
      const before = instance.getLayer(LABEL_LAYER) ? LABEL_LAYER : undefined;
      instance.addSource(MUNICIPALITY, { type: "geojson", data: empty() });
      instance.addSource(NETWORK, { type: "geojson", data: empty(), promoteId: "link_id" });
      for (const overlay of OVERLAYS) instance.addSource(overlay, { type: "geojson", data: empty() });
      instance.addSource("polys", { type: "geojson", data: empty(), promoteId: "id" });
      instance.addSource("draft", { type: "geojson", data: empty() });
      instance.addSource("edits-lines", { type: "geojson", data: empty() });
      // duas fontes do mesmo DEM: o MapLibre recomenda separar sombreamento e terreno 3D
      // Terreno 3D (z12) e sombreamento (z13) em fontes separadas, como o MapLibre recomenda.
      // Limitação conhecida: com o terreno ligado, o MapLibre projeta as linhas numa textura sobre
      // o relevo e em alguns pontos surgem "riscas" verticais claras; testado com DEM z9–z14 e
      // não depende dos dados de altitude (sem picos nos tiles). Por isso o 3D está como beta.
      for (const [id, maxzoom] of [["dem-hillshade", 13], ["dem-terrain", 12]] as const) {
        instance.addSource(id, {
          type: "raster-dem",
          tiles: [DEM_TILES],
          encoding: "terrarium",
          tileSize: 256,
          maxzoom,
          attribution: DEM_ATTRIBUTION,
        });
      }

      const add = (layer: Parameters<MapLibreMap["addLayer"]>[0], below = true) =>
        instance.addLayer(layer, below ? before : undefined);

      // sombreamento do relevo, por baixo de tudo (só a luz e a sombra das encostas)
      add({
        id: "relevo",
        type: "hillshade",
        source: "dem-hillshade",
        layout: { visibility: "none" },
        paint: {
          "hillshade-exaggeration": 0.55,
          "hillshade-shadow-color": "#000000",
          "hillshade-highlight-color": "rgba(244,246,245,0.22)",
          "hillshade-accent-color": "#0B0F0E",
          "hillshade-illumination-direction": 315,
        },
      });
      add({ id: "municipality-fill", type: "fill", source: MUNICIPALITY, paint: { "fill-color": "#F4F6F5", "fill-opacity": 0.015 } });
      // áreas (abaixo da rede): inundação e risco
      add({
        id: "inundacao",
        type: "fill",
        source: "inundacao",
        layout: { visibility: "none" },
        paint: { "fill-color": OVERLAY_COLOR.inundacao, "fill-opacity": ["match", ["get", "categoria"], "Alta", 0.3, 0.14] },
      });
      add({
        id: "risco",
        type: "fill",
        source: "risco",
        layout: { visibility: "none" },
        paint: { "fill-color": OVERLAY_COLOR.risco, "fill-opacity": ["match", ["get", "categoria"], "Muito alto", 0.5, 0.32] },
      });
      add({ id: "risco-line", type: "line", source: "risco", layout: { visibility: "none" }, paint: { "line-color": OVERLAY_COLOR.risco, "line-width": 1 } });
      add({
        id: "links",
        type: "line",
        source: NETWORK,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": lineColor(), "line-width": lineWidth(), "line-opacity": lineOpacity() },
      });
      // rede dentro do polígono selecionado, por cima (o resto escurece)
      add({ id: "links-in", type: "line", source: NETWORK, filter: NO_LINK, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": BUFFER_GRAY } });
      // camada invisível e larga só para facilitar o clique em linhas finas
      add({ id: "links-hit", type: "line", source: NETWORK, paint: { "line-color": "#000", "line-opacity": 0, "line-width": 12 } });
      add({
        id: "links-selected-glow",
        type: "line",
        source: NETWORK,
        filter: NO_LINK,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#F4F6F5", "line-opacity": 0.18, "line-width": lineWidth(9), "line-blur": 6 },
      });
      add({ id: "links-selected", type: "line", source: NETWORK, filter: NO_LINK, layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": "#F4F6F5", "line-width": lineWidth(3) } });
      // edições da rede: vias removidas, interditadas e redesenhadas (sobre a rede) e vias novas
      const editLine = (id: string, color: string, dash: number[], scale: number, opacity = 1) =>
        add({
          id,
          type: "line",
          source: NETWORK,
          filter: NO_LINK,
          layout: { "line-cap": "butt", "line-join": "round" },
          paint: { "line-color": color, "line-width": lineWidth(scale), "line-dasharray": dash, "line-opacity": opacity },
        });
      editLine("edit-removed", EDIT_COLORS.remove, [1.2, 1], 2.2);
      editLine("edit-closed", EDIT_COLORS.close, [2.2, 1.2], 2.2);
      editLine("edit-rerouted", EDIT_COLORS.remove, [0.6, 1.6], 1.6, 0.75);
      add({
        id: "edit-new-glow",
        type: "line",
        source: "edits-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": EDIT_COLORS.add, "line-opacity": 0.35, "line-width": ["interpolate", ["linear"], ["zoom"], 11, 5, 17, 14], "line-blur": 3 },
      });
      add({
        id: "edit-new",
        type: "line",
        source: "edits-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#F4F6F5", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.8, 17, 5] },
      });
      add({ id: "municipality-outline", type: "line", source: MUNICIPALITY, paint: { "line-color": "rgba(244,246,245,0.5)", "line-width": 1.2, "line-dasharray": [4, 3] } });
      // polígonos do cenário
      add({
        id: "polys-fill",
        type: "fill",
        source: "polys",
        paint: { "fill-color": ["case", ["boolean", ["feature-state", "selected"], false], "rgba(43,212,107,.08)", "rgba(59,140,255,.07)"] },
      });
      add({
        id: "polys-line",
        type: "line",
        source: "polys",
        paint: {
          "line-color": ["case", ["boolean", ["feature-state", "selected"], false], "#2BD46B", "rgba(244,246,245,.7)"],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2, 1.2],
        },
      });
      // pontos e rótulos (acima de tudo)
      add(
        {
          id: "saude",
          type: "circle",
          source: "saude",
          layout: { visibility: "none" },
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 2.5, 16, 6],
            "circle-color": OVERLAY_COLOR.saude,
            "circle-opacity": ["case", ["==", ["get", "sus"], true], 1, 0.55],
            "circle-stroke-color": "#07090A",
            "circle-stroke-width": 1,
          },
        },
        false,
      );
      add(
        {
          id: "escolas",
          type: "circle",
          source: "escolas",
          layout: { visibility: "none" },
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 11, 3, 16, 7],
            "circle-color": OVERLAY_COLOR.escolas,
            "circle-stroke-color": "#07090A",
            "circle-stroke-width": 1.5,
          },
        },
        false,
      );
      add(
        {
          id: "polys-label",
          type: "symbol",
          source: "polys",
          layout: {
            "text-field": ["concat", ["get", "code"], "  ", ["upcase", ["get", "name"]]],
            "text-font": ["Noto Sans Regular"],
            "text-size": 11,
            "text-letter-spacing": 0.08,
          },
          paint: { "text-color": "#F4F6F5", "text-halo-color": "rgba(10,13,14,.92)", "text-halo-width": 6 },
        },
        false,
      );
      add({ id: "draft-fill", type: "fill", source: "draft", filter: ["==", ["geometry-type"], "Polygon"], paint: { "fill-color": "rgba(43,212,107,.10)" } }, false);
      add({ id: "draft-line", type: "line", source: "draft", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#2BD46B", "line-width": 1.6, "line-dasharray": [2, 1.5] } }, false);
      add(
        {
          id: "draft-points",
          type: "circle",
          source: "draft",
          filter: ["==", ["geometry-type"], "Point"],
          paint: {
            "circle-radius": ["case", ["get", "first"], 6, ["==", ["get", "snapped"], true], 5, 3.5],
            "circle-color": [
              "case",
              ["get", "first"],
              "#2BD46B",
              ["==", ["get", "snapped"], true],
              "#2BD46B",
              ["==", ["get", "snapped"], false],
              "#FFA53B",
              "#F4F6F5",
            ],
            "circle-stroke-color": "#07090A",
            "circle-stroke-width": ["case", ["==", ["get", "snapped"], null], 0, 1.5],
          },
        },
        false,
      );
    });

    instance.on("mousemove", (e: MapMouseEvent) => {
      live.current.onCursor?.([e.lngLat.lng, e.lngLat.lat], instance.getZoom());
      const drawing = live.current.tool === "draw" || live.current.tool === "line";
      if (drawing && draft.current.length) {
        cursor.current =
          live.current.tool === "line" ? snapToNetwork(instance, e.point.x, e.point.y).at : [e.lngLat.lng, e.lngLat.lat];
        renderDraft();
      }
    });

    const popup = new Popup({ closeButton: false, className: "qc-popup", maxWidth: "260px" });
    instance.on("click", (event: MapMouseEvent) => {
      // via nova: cada clique é um vértice, encaixado na rede; clicar no último ponto termina
      if (live.current.tool === "line") {
        const pts = draft.current;
        const last = pts[pts.length - 1];
        if (last && pts.length >= 2) {
          const a = instance.project(last as [number, number]);
          if (Math.hypot(a.x - event.point.x, a.y - event.point.y) < CLOSE_PX) return completeDraft();
        }
        const point = snapToNetwork(instance, event.point.x, event.point.y);
        pts.push(point.at);
        snapped.current.push(point.snapped);
        live.current.onDraftChange?.(pts.length);
        renderDraft();
        return;
      }
      if (live.current.tool === "pick") {
        const [hit] = instance.queryRenderedFeatures(event.point, { layers: ["links-hit"] });
        if (hit) live.current.onPickLink?.(hit.properties as LinkProperties);
        return;
      }
      // desenhando: cada clique é um vértice; perto do primeiro, fecha
      if (live.current.tool === "draw") {
        const pts = draft.current;
        const first = pts[0];
        if (first && pts.length >= 3) {
          const a = instance.project(first as [number, number]);
          if (Math.hypot(a.x - event.point.x, a.y - event.point.y) < CLOSE_PX) return completeDraft();
        }
        pts.push([event.lngLat.lng, event.lngLat.lat]);
        live.current.onDraftChange?.(pts.length);
        renderDraft();
        return;
      }
      const overlayLayers = (["escolas", "saude", "risco", "inundacao"] as const).filter(
        (id) => instance.getLayer(id) && instance.getLayoutProperty(id, "visibility") === "visible",
      );
      const hits = instance.queryRenderedFeatures(event.point, { layers: ["links-hit", "polys-fill", ...overlayLayers] });
      const point = hits.find((h) => h.layer.id === "escolas" || h.layer.id === "saude");
      const link = hits.find((h) => h.layer.id === "links-hit");
      const area = hits.find((h) => h.layer.id === "risco" || h.layer.id === "inundacao");
      const polygon = hits.find((h) => h.layer.id === "polys-fill");
      const shown = point ?? (link ? undefined : area);
      if (shown) {
        popup.setLngLat(event.lngLat).setHTML(popupHtml(shown.layer.id as Overlay, shown.properties)).addTo(instance);
      } else popup.remove();
      if (link && !point) {
        live.current.onSelect({ properties: link.properties as LinkProperties, lngLat: [event.lngLat.lng, event.lngLat.lat] });
      } else if (!link) live.current.onSelect(null);
      if (live.current.onSelectPolygon && (polygon || !link)) {
        live.current.onSelectPolygon((polygon?.properties.id as string | undefined) ?? null);
      }
    });

    instance.on("dblclick", (e: MapMouseEvent) => {
      if (live.current.tool !== "draw" && live.current.tool !== "line") return;
      e.preventDefault();
      draft.current.pop(); // o duplo clique já adicionou um vértice extra
      snapped.current.pop();
      completeDraft();
    });

    const onKey = (event: KeyboardEvent) => {
      const t = live.current.tool;
      if (t !== "draw" && t !== "line" && t !== "pick") return;
      if (event.key === "Enter") completeDraft();
      if (event.key === "Backspace" && draft.current.length && !(event.target instanceof HTMLInputElement)) {
        draft.current.pop();
        snapped.current.pop();
        live.current.onDraftChange?.(draft.current.length);
        renderDraft();
      }
      if (event.key === "Escape") {
        clearDraft();
        live.current.onDrawCancel?.();
      }
    };
    window.addEventListener("keydown", onKey);

    const idleCursor = () => (live.current.tool === "draw" || live.current.tool === "line" ? "crosshair" : "");
    for (const id of ["links-hit", "saude", "escolas"]) {
      instance.on("mouseenter", id, () => {
        if (live.current.tool === "select" || live.current.tool === "pick") instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", id, () => {
        instance.getCanvas().style.cursor = idleCursor();
      });
    }

    map.current = instance;
    return () => {
      window.removeEventListener("keydown", onKey);
      instance.remove();
      map.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- o mapa é criado uma vez
  }, []);

  const whenReady = (fn: (m: MapLibreMap) => void) => {
    const instance = map.current;
    if (!instance) return;
    if (instance.getLayer("links")) fn(instance);
    else instance.once("load", () => fn(instance));
  };

  // dados da rede e do município
  useEffect(() => {
    whenReady((m) => {
      (m.getSource(NETWORK) as GeoJSONSource).setData(data.network);
      (m.getSource(MUNICIPALITY) as GeoJSONSource).setData(data.municipality);
      // enquadra só na primeira carga: trocar mapa atual ↔ cenário não mexe na vista
      if (!fitted.current) fitAll();
      fitted.current = true;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fitAll depende só de `data`
  }, [data]);

  // simbologia: cores sintáticas quando há análise; delta no cenário de laboratório
  useEffect(() => {
    whenReady((m) => {
      let color: ExpressionSpecification;
      let width: ExpressionSpecification;
      let sortKey: ExpressionSpecification | undefined;
      if (data.scenario && symbology === "delta") {
        [color, width, sortKey] = [deltaColor(measure, radius), deltaWidth(measure, radius), deltaSortKey(measure, radius)];
      } else if (data.analysis || data.scenario) {
        [color, width, sortKey] = [syntaxColor(measure, radius, BUFFER_GRAY), syntaxWidth(measure, radius), syntaxSortKey(measure, radius)];
      } else {
        [color, width] = [lineColor(tone), lineWidth()];
      }
      for (const id of ["links", "links-in"]) {
        m.setPaintProperty(id, "line-color", color);
        if (sortKey) m.setLayoutProperty(id, "line-sort-key", sortKey);
      }
      m.setPaintProperty("links", "line-width", width);
      m.setPaintProperty("links-in", "line-width", ["*", 1.15, width] as ExpressionSpecification);
    });
     
  }, [data.analysis, data.scenario, measure, radius, symbology, tone]);

  // camadas ligadas/desligadas (as territoriais são baixadas na primeira vez que ligam)
  useEffect(() => {
    whenReady((m) => {
      const show = (on: boolean) => (on ? "visible" : "none");
      for (const id of ["links", "links-in"]) m.setLayoutProperty(id, "visibility", show(flags.net));
      const zoneFilter: FilterSpecification | null = flags.ent ? null : ["==", ["get", "zone"], "result"];
      m.setFilter("links", zoneFilter);
      m.setFilter("links-hit", zoneFilter);
      m.setLayoutProperty("municipality-outline", "visibility", show(flags.lim));
      m.setLayoutProperty("polys-label", "visibility", show(flags.lab));
      m.setLayoutProperty("relevo", "visibility", show(flags.relevo || flags.terrain3d));
      const has3d = Boolean(m.getTerrain());
      if (flags.terrain3d && !has3d) {
        m.setTerrain({ source: "dem-terrain", exaggeration: TERRAIN_EXAGGERATION });
        m.easeTo({ pitch: TERRAIN_PITCH, bearing: m.getBearing() || -20, duration: 900 });
      } else if (!flags.terrain3d && has3d) {
        m.setTerrain(null);
        m.easeTo({ pitch: 0, bearing: 0, duration: 700 });
      }
      for (const overlay of OVERLAYS) {
        const on = flags[overlay];
        m.setLayoutProperty(overlay, "visibility", show(on));
        if (overlay === "risco") m.setLayoutProperty("risco-line", "visibility", show(on));
        if (on && !loaded.current.has(overlay)) {
          loaded.current.add(overlay);
          api<FeatureCollection>(OVERLAY_ENDPOINT[overlay])
            .then((fc) => (m.getSource(overlay) as GeoJSONSource | undefined)?.setData(fc))
            .catch(() => {
              loaded.current.delete(overlay);
              live.current.onOverlayError?.(overlay);
            });
        }
      }
    });
     
  }, [flags]);

  // ferramenta (desenho muda cursor e desliga o zoom do duplo clique)
  useEffect(() => {
    whenReady((m) => {
      const drawing = tool === "draw" || tool === "line";
      m.getCanvas().style.cursor = drawing ? "crosshair" : "";
      if (drawing) m.doubleClickZoom.disable();
      else m.doubleClickZoom.enable();
      if (draft.current.length) clearDraft(); // trocar de ferramenta descarta o rascunho
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- clearDraft só mexe em refs
  }, [tool]);

  // fundo do mapa e cores "de tinta" conforme o tom (escuro/claro)
  useEffect(() => {
    if (container.current) container.current.dataset.tone = tone;
    whenReady((m) => {
      if (!config.basemapStyleUrl) applyBasemap(m, basemap, theme);
      const ink = INK[tone];
      m.setPaintProperty("municipality-outline", "line-color", ink.outline);
      m.setPaintProperty("links-selected", "line-color", ink.ink);
      m.setPaintProperty("links-selected-glow", "line-color", ink.ink);
      m.setPaintProperty("links-selected-glow", "line-opacity", ink.glow);
      m.setPaintProperty("municipality-fill", "fill-color", ink.ink);
      m.setPaintProperty("polys-label", "text-color", ink.ink);
      m.setPaintProperty("polys-label", "text-halo-color", ink.halo);
      m.setPaintProperty("edit-new", "line-color", ink.ink);
      m.setPaintProperty("polys-line", "line-color", [
        "case",
        ["boolean", ["feature-state", "selected"], false],
        "#2BD46B",
        ink.poly,
      ] as ExpressionSpecification);
    });
  }, [basemap, theme, tone]);

  // edições da rede
  useEffect(() => {
    whenReady((m) => {
      const byIds = (ids: string[]): FilterSpecification =>
        ids.length ? ["in", ["get", "link_id"], ["literal", ids]] : NO_LINK;
      m.setFilter("edit-removed", byIds(idsOf(edits, "remove")));
      m.setFilter("edit-closed", byIds(idsOf(edits, "close")));
      m.setFilter("edit-rerouted", byIds(idsOf(edits, "reroute")));
      (m.getSource("edits-lines") as GeoJSONSource).setData(showNewLines ? editLines(edits) : empty());
    });
  }, [edits, showNewLines, data]);

  // pin do endereço buscado
  useEffect(() => {
    marker.current?.remove();
    marker.current = null;
    if (!pin) return;
    whenReady((m) => {
      const el = document.createElement("div");
      el.className = "qc-pin";
      el.innerHTML = '<span class="qc-pin-dot"></span><span class="qc-pin-label"></span>';
      (el.querySelector(".qc-pin-label") as HTMLElement).textContent = pin.label;
      marker.current = new Marker({ element: el, anchor: "bottom" }).setLngLat(pin.lngLat).addTo(m);
      m.flyTo({ center: pin.lngLat, zoom: Math.max(m.getZoom(), 17), duration: 900 });
    });
  }, [pin]);

  // polígonos
  useEffect(() => {
    whenReady((m) => (m.getSource("polys") as GeoJSONSource).setData(polygons ?? empty()));
     
  }, [polygons]);

  // polígono selecionado: destaca a rede dentro dele e enquadra
  useEffect(() => {
    whenReady((m) => {
      for (const f of polygons?.features ?? []) {
        m.setFeatureState({ source: "polys", id: f.properties.id }, { selected: f.properties.id === selectedPolygonId });
      }
      const selected = polygons?.features.find((f) => f.properties.id === selectedPolygonId);
      m.setPaintProperty("links", "line-opacity", selected ? 0.22 : lineOpacity());
      m.setFilter("links-in", selected ? (["within", selected.geometry] as unknown as FilterSpecification) : NO_LINK);
      const bounds = selected ? boundsOf([selected.geometry]) : null;
      if (bounds) {
        m.fitBounds(bounds, { padding: { top: 140, bottom: 80, left: 60, right: rightInset + 60 }, maxZoom: 16, duration: 600 });
      }
    });
     
  }, [selectedPolygonId, polygons, rightInset]);

  // destaca o trecho selecionado
  useEffect(() => {
    whenReady((m) => {
      const filter: FilterSpecification = ["==", ["get", "link_id"], selectedId ?? ""];
      m.setFilter("links-selected", filter);
      m.setFilter("links-selected-glow", filter);
    });
     
  }, [selectedId]);

  return <div ref={container} className="map" role="region" aria-label="Mapa sintático de Brusque" />;
});
