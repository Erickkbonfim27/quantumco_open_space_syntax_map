import "maplibre-gl/dist/maplibre-gl.css";

import {
  type FilterSpecification,
  type GeoJSONSource,
  Map as MapLibreMap,
  type MapMouseEvent,
  Popup,
  ScaleControl,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { FeatureCollection } from "geojson";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

import { config } from "../../config";
import { api } from "../../lib/api";
import { boundsOf } from "../../lib/geo";
import type { LinkProperties, Measure, RadiusKey, SnapshotData } from "../../lib/types";
import { darkBasemapStyle, LABEL_LAYER } from "./basemapStyle";
import { lineColor, lineOpacity, lineWidth } from "./highwayGroups";
import {
  deltaColor,
  deltaSortKey,
  deltaWidth,
  syntaxColor,
  syntaxSortKey,
  syntaxWidth,
} from "./syntaxPalette";

/** Entorno (sem classe) em cinza neutro, como no design. */
const BUFFER_GRAY = "#4A5155";
/** Passo da grade de pontos do fundo (px), igual ao design e ao CSS. */
const GRID = 36;

// O MapLibre 6 resolve o worker por uma URL dinâmica que o Vite não enxerga; registramos o
// arquivo explicitamente (ele é autocontido, sem imports).
setWorkerUrl(workerUrl);

const NETWORK = "network";
const MUNICIPALITY = "municipality";
const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

/** Camadas territoriais (dados abertos) que o mapa público liga sob demanda. */
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

export interface MapFlags {
  net: boolean;
  ent: boolean;
  lim: boolean;
  inundacao: boolean;
  risco: boolean;
  saude: boolean;
  escolas: boolean;
}

export interface Selection {
  properties: LinkProperties;
  lngLat: [number, number];
}

export interface MapViewHandle {
  zoomIn: () => void;
  zoomOut: () => void;
  fitAll: () => void;
}

interface MapViewProps {
  data: SnapshotData;
  measure: Measure;
  radius: RadiusKey;
  flags: MapFlags;
  selectedId: string | null;
  onSelect: (selection: Selection | null) => void;
  onCursor?: (lngLat: [number, number], zoom: number) => void;
  onOverlayError?: (overlay: Overlay) => void;
}

const escapeHtml = (text: string) =>
  text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

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

export const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(
  { data, measure, radius, flags, selectedId, onSelect, onCursor, onOverlayError },
  handleRef,
) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const live = useRef({ onSelect, onCursor, onOverlayError });
  const loaded = useRef(new Set<Overlay>());

  useEffect(() => {
    live.current = { onSelect, onCursor, onOverlayError };
  }, [onSelect, onCursor, onOverlayError]);

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
  }));

  // cria o mapa uma vez
  useEffect(() => {
    if (!container.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: config.basemapStyleUrl ?? darkBasemapStyle,
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
    instance.on("mousemove", (e) => {
      live.current.onCursor?.([e.lngLat.lng, e.lngLat.lat], instance.getZoom());
    });

    instance.on("load", () => {
      syncGrid();
      // a rede entra ANTES dos nomes de lugares, que ficam legíveis por cima
      const before = instance.getLayer(LABEL_LAYER) ? LABEL_LAYER : undefined;
      instance.addSource(MUNICIPALITY, { type: "geojson", data: empty() });
      instance.addSource(NETWORK, { type: "geojson", data: empty(), promoteId: "link_id" });
      for (const overlay of OVERLAYS) instance.addSource(overlay, { type: "geojson", data: empty() });

      instance.addLayer(
        { id: "municipality-fill", type: "fill", source: MUNICIPALITY,
          paint: { "fill-color": "#F4F6F5", "fill-opacity": 0.015 } },
        before,
      ); // prettier-ignore
      // áreas (abaixo da rede): inundação e risco
      instance.addLayer(
        {
          id: "inundacao",
          type: "fill",
          source: "inundacao",
          layout: { visibility: "none" },
          paint: {
            "fill-color": OVERLAY_COLOR.inundacao,
            "fill-opacity": ["match", ["get", "categoria"], "Alta", 0.3, 0.14],
          },
        },
        before,
      );
      instance.addLayer(
        {
          id: "risco",
          type: "fill",
          source: "risco",
          layout: { visibility: "none" },
          paint: {
            "fill-color": OVERLAY_COLOR.risco,
            "fill-opacity": ["match", ["get", "categoria"], "Muito alto", 0.5, 0.32],
          },
        },
        before,
      );
      instance.addLayer(
        { id: "risco-line", type: "line", source: "risco", layout: { visibility: "none" },
          paint: { "line-color": OVERLAY_COLOR.risco, "line-width": 1 } },
        before,
      ); // prettier-ignore
      instance.addLayer(
        {
          id: "links",
          type: "line",
          source: NETWORK,
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": lineColor(),
            "line-width": lineWidth(),
            "line-opacity": lineOpacity(),
          },
        },
        before,
      );
      // camada invisível e larga só para facilitar o clique em linhas finas
      instance.addLayer(
        { id: "links-hit", type: "line", source: NETWORK,
          paint: { "line-color": "#000", "line-opacity": 0, "line-width": 12 } },
        before,
      ); // prettier-ignore
      instance.addLayer(
        {
          id: "links-selected-glow",
          type: "line",
          source: NETWORK,
          filter: ["==", ["get", "link_id"], ""],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#F4F6F5", "line-opacity": 0.18, "line-width": lineWidth(9), "line-blur": 6 },
        },
        before,
      );
      instance.addLayer(
        {
          id: "links-selected",
          type: "line",
          source: NETWORK,
          filter: ["==", ["get", "link_id"], ""],
          layout: { "line-cap": "round", "line-join": "round" },
          paint: { "line-color": "#F4F6F5", "line-width": lineWidth(3) },
        },
        before,
      );
      instance.addLayer(
        {
          id: "municipality-outline",
          type: "line",
          source: MUNICIPALITY,
          paint: { "line-color": "rgba(244,246,245,0.5)", "line-width": 1.2, "line-dasharray": [4, 3] },
        },
        before,
      );
      // pontos (acima da rede): saúde e escolas
      instance.addLayer({
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
      });
      instance.addLayer({
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
      });
    });

    const popup = new Popup({ closeButton: false, className: "qc-popup", maxWidth: "260px" });
    instance.on("click", (event: MapMouseEvent) => {
      const overlayLayers = (["escolas", "saude", "risco", "inundacao"] as const).filter(
        (id) => instance.getLayer(id) && instance.getLayoutProperty(id, "visibility") === "visible",
      );
      const hits = instance.queryRenderedFeatures(event.point, { layers: ["links-hit", ...overlayLayers] });
      const point = hits.find((h) => h.layer.id === "escolas" || h.layer.id === "saude");
      const link = hits.find((h) => h.layer.id === "links-hit");
      const area = hits.find((h) => h.layer.id === "risco" || h.layer.id === "inundacao");
      const shown = point ?? (link ? undefined : area);
      if (shown) {
        popup
          .setLngLat(event.lngLat)
          .setHTML(popupHtml(shown.layer.id as Overlay, shown.properties))
          .addTo(instance);
      } else popup.remove();
      if (link && !point) {
        live.current.onSelect({
          properties: link.properties as LinkProperties,
          lngLat: [event.lngLat.lng, event.lngLat.lat],
        });
      } else if (!link) live.current.onSelect(null);
    });
    for (const id of ["links-hit", "saude", "escolas"]) {
      instance.on("mouseenter", id, () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", id, () => {
        instance.getCanvas().style.cursor = "";
      });
    }

    map.current = instance;
    return () => {
      instance.remove();
      map.current = null;
    };
  }, []);

  // carrega os dados quando o estilo estiver pronto
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      (instance.getSource(NETWORK) as GeoJSONSource).setData(data.network);
      (instance.getSource(MUNICIPALITY) as GeoJSONSource).setData(data.municipality);
      fitAll();
    };
    if (instance.getSource(NETWORK)) apply();
    else instance.once("load", apply);
    // fitAll depende só de `data`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // simbologia: cores sintáticas quando há análise; senão, hierarquia em tons neutros
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (!instance.getLayer("links")) return;
      if (data.scenario) {
        instance.setPaintProperty("links", "line-color", deltaColor(measure, radius));
        instance.setPaintProperty("links", "line-width", deltaWidth(measure, radius));
        instance.setLayoutProperty("links", "line-sort-key", deltaSortKey(measure, radius));
      } else if (data.analysis) {
        instance.setPaintProperty("links", "line-color", syntaxColor(measure, radius, BUFFER_GRAY));
        instance.setPaintProperty("links", "line-width", syntaxWidth(measure, radius));
        instance.setLayoutProperty("links", "line-sort-key", syntaxSortKey(measure, radius));
      } else {
        instance.setPaintProperty("links", "line-color", lineColor());
        instance.setPaintProperty("links", "line-width", lineWidth());
      }
    };
    if (instance.getLayer("links")) apply();
    else instance.once("load", apply);
  }, [data.analysis, data.scenario, measure, radius]);

  // camadas ligadas/desligadas (as territoriais são baixadas na primeira vez que ligam)
  useEffect(() => {
    const instance = map.current;
    if (!instance) return;
    const apply = () => {
      if (!instance.getLayer("links")) return;
      const show = (on: boolean) => (on ? "visible" : "none");
      instance.setLayoutProperty("links", "visibility", show(flags.net));
      const zoneFilter: FilterSpecification | null = flags.ent ? null : ["==", ["get", "zone"], "result"];
      instance.setFilter("links", zoneFilter);
      instance.setFilter("links-hit", zoneFilter);
      instance.setLayoutProperty("municipality-outline", "visibility", show(flags.lim));
      for (const overlay of OVERLAYS) {
        const on = flags[overlay];
        instance.setLayoutProperty(overlay, "visibility", show(on));
        if (overlay === "risco") instance.setLayoutProperty("risco-line", "visibility", show(on));
        if (on && !loaded.current.has(overlay)) {
          loaded.current.add(overlay);
          api<FeatureCollection>(OVERLAY_ENDPOINT[overlay])
            .then((fc) => (instance.getSource(overlay) as GeoJSONSource | undefined)?.setData(fc))
            .catch(() => {
              loaded.current.delete(overlay);
              live.current.onOverlayError?.(overlay);
            });
        }
      }
    };
    if (instance.getLayer("links")) apply();
    else instance.once("load", apply);
  }, [flags]);

  // destaca o trecho selecionado
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getLayer("links-selected")) return;
    const filter: FilterSpecification = ["==", ["get", "link_id"], selectedId ?? ""];
    instance.setFilter("links-selected", filter);
    instance.setFilter("links-selected-glow", filter);
  }, [selectedId]);

  return <div ref={container} className="map" role="region" aria-label="Mapa da rede viária" />;
});
