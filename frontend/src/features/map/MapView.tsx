import "maplibre-gl/dist/maplibre-gl.css";

import {
  type GeoJSONSource,
  Map as MapLibreMap,
  type MapLayerMouseEvent,
  type MapMouseEvent,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { FeatureCollection } from "geojson";
import { useEffect, useRef } from "react";

import { config } from "../../config";
import { darkBasemapStyle } from "./basemapStyle";
import { boundsOf } from "../../lib/geo";
import type { LinkProperties, Measure, RadiusKey, SnapshotData } from "../../lib/types";
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

// O MapLibre 6 resolve o worker por uma URL dinâmica que o Vite não enxerga; registramos o
// arquivo explicitamente (ele é autocontido, sem imports).
setWorkerUrl(workerUrl);

const NETWORK = "network";
const MUNICIPALITY = "municipality";
const empty = (): FeatureCollection => ({ type: "FeatureCollection", features: [] });

export interface Selection {
  properties: LinkProperties;
  lngLat: [number, number];
}

interface MapViewProps {
  data: SnapshotData;
  measure: Measure;
  radius: RadiusKey;
  selectedId: string | null;
  onSelect: (selection: Selection | null) => void;
}

export function MapView({ data, measure, radius, selectedId, onSelect }: MapViewProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelect);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  // cria o mapa uma vez
  useEffect(() => {
    if (!container.current) return;
    const instance = new MapLibreMap({
      container: container.current,
      style: config.basemapStyleUrl ?? darkBasemapStyle,
      center: [-48.917, -27.098],
      zoom: 12,
      attributionControl: { compact: true },
    });
    instance.addControl(new NavigationControl({ showCompass: false }), "top-right");
    instance.addControl(new ScaleControl({ unit: "metric" }), "bottom-right");

    instance.on("load", () => {
      instance.addSource(MUNICIPALITY, { type: "geojson", data: empty() });
      instance.addSource(NETWORK, { type: "geojson", data: empty(), promoteId: "link_id" });

      instance.addLayer({
        id: "municipality-fill",
        type: "fill",
        source: MUNICIPALITY,
        paint: { "fill-color": "#F4F6F5", "fill-opacity": 0.015 },
      });
      instance.addLayer({
        id: "links",
        type: "line",
        source: NETWORK,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": lineColor(),
          "line-width": lineWidth(),
          "line-opacity": lineOpacity(),
        },
      });
      // camada invisível e larga só para facilitar o clique em linhas finas
      instance.addLayer({
        id: "links-hit",
        type: "line",
        source: NETWORK,
        paint: { "line-color": "#000", "line-opacity": 0, "line-width": 12 },
      });
      instance.addLayer({
        id: "links-selected",
        type: "line",
        source: NETWORK,
        filter: ["==", ["get", "link_id"], ""],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": "#F4F6F5", "line-width": lineWidth(3) },
      });
      instance.addLayer({
        id: "municipality-outline",
        type: "line",
        source: MUNICIPALITY,
        paint: { "line-color": "rgba(244,246,245,0.5)", "line-width": 1.2, "line-dasharray": [4, 3] },
      });
    });

    instance.on("click", "links-hit", (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      if (!feature) return;
      onSelectRef.current({
        properties: feature.properties as LinkProperties,
        lngLat: [event.lngLat.lng, event.lngLat.lat],
      });
    });
    instance.on("click", (event: MapMouseEvent) => {
      const hits = instance.queryRenderedFeatures(event.point, { layers: ["links-hit"] });
      if (hits.length === 0) onSelectRef.current(null);
    });
    instance.on("mouseenter", "links-hit", () => {
      instance.getCanvas().style.cursor = "pointer";
    });
    instance.on("mouseleave", "links-hit", () => {
      instance.getCanvas().style.cursor = "";
    });

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
      const bounds = boundsOf(data.municipality.features.map((f) => f.geometry));
      if (bounds) {
        // o painel flutuante cobre a esquerda (desktop) ou a base (celular)
        const mobile = window.matchMedia("(max-width: 760px)").matches;
        const padding = mobile
          ? { top: 24, right: 24, bottom: window.innerHeight * 0.5, left: 24 }
          : { top: 40, right: 80, bottom: 40, left: 420 };
        instance.fitBounds(bounds, { padding, duration: 0 });
      }
    };
    if (instance.getSource(NETWORK)) apply();
    else instance.once("load", apply);
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

  // destaca o trecho selecionado
  useEffect(() => {
    const instance = map.current;
    if (!instance?.getLayer("links-selected")) return;
    instance.setFilter("links-selected", ["==", ["get", "link_id"], selectedId ?? ""]);
  }, [selectedId]);

  return <div ref={container} className="map" role="region" aria-label="Mapa da rede viária" />;
}
