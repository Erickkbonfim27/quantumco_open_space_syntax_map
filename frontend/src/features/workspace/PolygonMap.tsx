import "maplibre-gl/dist/maplibre-gl.css";

import type { Feature, FeatureCollection, LineString, Polygon, Position } from "geojson";
import {
  type ExpressionSpecification,
  type GeoJSONSource,
  Map as MapLibreMap,
  type MapLayerMouseEvent,
  type MapMouseEvent,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { config } from "../../config";
import { boundsOf } from "../../lib/geo";
import type { PolygonCollection } from "../../lib/platformTypes";
import type { Measure, SnapshotData } from "../../lib/types";
import { darkBasemapStyle } from "../map/basemapStyle";
import { syntaxColor, syntaxSortKey, syntaxWidth } from "../map/syntaxPalette";

setWorkerUrl(workerUrl);

export interface MapFlags {
  net: boolean;
  ent: boolean;
  lim: boolean;
  lab: boolean;
}

export interface PolygonMapHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitAll: () => void;
}

interface PolygonMapProps {
  data: SnapshotData;
  polygons: PolygonCollection;
  measure: Measure;
  flags: MapFlags;
  tool: "select" | "draw";
  selectedId: string | null;
  rightInset: number; // painel de seleção aberto à direita
  onSelect: (id: string | null) => void;
  onDrawComplete: (ring: Position[]) => void;
  onDrawCancel: () => void;
  onDraftChange: (vertices: number) => void;
  onCursor: (lngLat: [number, number], zoom: number) => void;
}

const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });
const BUFFER_GRAY = "#4A5155";
const CLOSE_PX = 12;

export const PolygonMap = forwardRef<PolygonMapHandle, PolygonMapProps>(function PolygonMap(
  props,
  handleRef,
) {
  const { data, polygons, measure, flags, tool, selectedId, rightInset } = props;
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const draft = useRef<Position[]>([]);
  const cursor = useRef<Position | null>(null);
  const live = useRef(props);
  live.current = props;

  const fitAll = () => {
    const instance = map.current;
    const bounds = boundsOf(data.municipality.features.map((f) => f.geometry));
    if (instance && bounds) instance.fitBounds(bounds, { padding: 40, duration: 600 });
  };

  useImperativeHandle(handleRef, () => ({
    zoomIn: () => map.current?.zoomIn(),
    zoomOut: () => map.current?.zoomOut(),
    fitAll,
  }));

  const renderDraft = () => {
    const source = map.current?.getSource("draft") as GeoJSONSource | undefined;
    if (!source) return;
    const pts = draft.current;
    const features: Feature[] = pts.map((p, i) => ({
      type: "Feature",
      properties: { first: i === 0 },
      geometry: { type: "Point", coordinates: p },
    }));
    const path = cursor.current ? [...pts, cursor.current] : pts;
    if (path.length >= 2) {
      features.push({
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: path } as LineString,
      });
    }
    const start = path[0];
    if (path.length >= 3 && start) {
      features.push({
        type: "Feature",
        properties: {},
        geometry: { type: "Polygon", coordinates: [[...path, start]] } as Polygon,
      });
    }
    source.setData({ type: "FeatureCollection", features });
  };

  const completeDraft = () => {
    const pts = draft.current;
    const start = pts[0];
    if (pts.length < 3 || !start) return;
    draft.current = [];
    cursor.current = null;
    renderDraft();
    live.current.onDraftChange(0);
    live.current.onDrawComplete([...pts, start]);
  };

  // cria o mapa
  useEffect(() => {
    if (!container.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: config.basemapStyleUrl ?? darkBasemapStyle,
      center: [-48.917, -27.098],
      zoom: 11.5,
      attributionControl: false,
    });
    map.current = instance;

    instance.on("load", () => {
      instance.addSource("muni", { type: "geojson", data: data.municipality });
      instance.addSource("net", { type: "geojson", data: data.network });
      instance.addSource("polys", { type: "geojson", data: empty(), promoteId: "id" });
      instance.addSource("draft", { type: "geojson", data: empty() });

      instance.addLayer({
        id: "links",
        type: "line",
        source: "net",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": BUFFER_GRAY, "line-width": 1 },
      });
      instance.addLayer({
        id: "links-in",
        type: "line",
        source: "net",
        filter: ["==", ["get", "link_id"], ""],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": BUFFER_GRAY, "line-width": 1 },
      });
      instance.addLayer({
        id: "muni-line",
        type: "line",
        source: "muni",
        paint: { "line-color": "rgba(244,246,245,.45)", "line-width": 1.2, "line-dasharray": [4, 3] },
      });
      instance.addLayer({
        id: "polys-fill",
        type: "fill",
        source: "polys",
        paint: {
          "fill-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "rgba(43,212,107,.08)",
            "rgba(59,140,255,.07)",
          ],
        },
      });
      instance.addLayer({
        id: "polys-line",
        type: "line",
        source: "polys",
        paint: {
          "line-color": [
            "case",
            ["boolean", ["feature-state", "selected"], false],
            "#2BD46B",
            "rgba(244,246,245,.7)",
          ],
          "line-width": ["case", ["boolean", ["feature-state", "selected"], false], 2, 1.2],
        },
      });
      instance.addLayer({
        id: "polys-label",
        type: "symbol",
        source: "polys",
        layout: {
          "text-field": ["concat", ["get", "code"], "  ", ["upcase", ["get", "name"]]],
          "text-font": ["Noto Sans Regular"],
          "text-size": 11,
          "text-letter-spacing": 0.08,
        },
        paint: {
          "text-color": "#F4F6F5",
          "text-halo-color": "rgba(10,13,14,.92)",
          "text-halo-width": 6,
        },
      });
      instance.addLayer({
        id: "draft-fill",
        type: "fill",
        source: "draft",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "rgba(43,212,107,.10)" },
      });
      instance.addLayer({
        id: "draft-line",
        type: "line",
        source: "draft",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#2BD46B", "line-width": 1.6, "line-dasharray": [2, 1.5] },
      });
      instance.addLayer({
        id: "draft-points",
        type: "circle",
        source: "draft",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": ["case", ["get", "first"], 6, 3.5],
          "circle-color": ["case", ["get", "first"], "#2BD46B", "#F4F6F5"],
        },
      });
      fitAll();
    });

    instance.on("mousemove", (e: MapMouseEvent) => {
      live.current.onCursor([e.lngLat.lng, e.lngLat.lat], instance.getZoom());
      if (live.current.tool === "draw" && draft.current.length) {
        cursor.current = [e.lngLat.lng, e.lngLat.lat];
        renderDraft();
      }
    });

    instance.on("click", (e: MapMouseEvent) => {
      if (live.current.tool === "draw") {
        const pts = draft.current;
        const first = pts[0];
        if (first && pts.length >= 3) {
          const a = instance.project(first as [number, number]);
          if (Math.hypot(a.x - e.point.x, a.y - e.point.y) < CLOSE_PX) return completeDraft();
        }
        pts.push([e.lngLat.lng, e.lngLat.lat]);
        live.current.onDraftChange(pts.length);
        renderDraft();
        return;
      }
      const hit = instance.queryRenderedFeatures(e.point, { layers: ["polys-fill"] });
      const id = hit[0]?.properties?.id as string | undefined;
      live.current.onSelect(id ?? null);
    });

    instance.on("dblclick", (e: MapLayerMouseEvent | MapMouseEvent) => {
      if (live.current.tool !== "draw") return;
      e.preventDefault();
      draft.current.pop(); // o duplo clique já adicionou um vértice extra
      completeDraft();
    });

    const onKey = (event: KeyboardEvent) => {
      if (live.current.tool !== "draw") return;
      if (event.key === "Enter") completeDraft();
      if (event.key === "Escape") {
        draft.current = [];
        cursor.current = null;
        renderDraft();
        live.current.onDraftChange(0);
        live.current.onDrawCancel();
      }
    };
    window.addEventListener("keydown", onKey);

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

  // polígonos
  useEffect(() => {
    whenReady((m) => (m.getSource("polys") as GeoJSONSource).setData(polygons));
  }, [polygons]);

  // simbologia sintática (raio n, como no design) e camadas ligadas/desligadas
  useEffect(() => {
    whenReady((m) => {
      const color = syntaxColor(measure, "n", BUFFER_GRAY);
      const width = syntaxWidth(measure, "n");
      for (const id of ["links", "links-in"]) {
        m.setPaintProperty(id, "line-color", color);
        m.setLayoutProperty(id, "line-sort-key", syntaxSortKey(measure, "n"));
      }
      m.setPaintProperty("links", "line-width", width);
      m.setPaintProperty("links-in", "line-width", ["*", 1.15, width] as ExpressionSpecification);
      m.setLayoutProperty("links", "visibility", flags.net ? "visible" : "none");
      m.setLayoutProperty("links-in", "visibility", flags.net ? "visible" : "none");
      m.setFilter("links", flags.ent ? null : ["==", ["get", "zone"], "result"]);
      m.setLayoutProperty("muni-line", "visibility", flags.lim ? "visible" : "none");
      m.setLayoutProperty("polys-label", "visibility", flags.lab ? "visible" : "none");
      m.getCanvas().style.cursor = tool === "draw" ? "crosshair" : "";
      if (tool === "draw") m.doubleClickZoom.disable();
      else m.doubleClickZoom.enable();
    });
  }, [measure, flags, tool]);

  // seleção: destaca a rede dentro do polígono e enquadra
  useEffect(() => {
    whenReady((m) => {
      for (const f of polygons.features) {
        m.setFeatureState({ source: "polys", id: f.properties.id }, { selected: f.properties.id === selectedId });
      }
      const selected = polygons.features.find((f) => f.properties.id === selectedId);
      m.setPaintProperty("links", "line-opacity", selected ? 0.22 : 1);
      m.setFilter(
        "links-in",
        selected ? (["within", selected.geometry] as unknown as ExpressionSpecification) : ["==", ["get", "link_id"], ""],
      );
      if (selected) {
        const bounds = boundsOf([selected.geometry]);
        if (bounds) {
          m.fitBounds(bounds, {
            padding: { top: 140, bottom: 80, left: 60, right: rightInset + 60 },
            maxZoom: 16,
            duration: 600,
          });
        }
      }
    });
  }, [selectedId, polygons, rightInset]);

  return <div ref={container} className="poly-map" role="region" aria-label="Mapa do cenário" />;
});
