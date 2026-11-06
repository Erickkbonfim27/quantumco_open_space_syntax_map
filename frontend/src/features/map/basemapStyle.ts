import type { Map as MapLibreMap, StyleSpecification } from "maplibre-gl";

/**
 * Fundos do mapa. Todos vivem no MESMO estilo (camadas ligadas/desligadas), para trocar de fundo
 * sem recarregar a rede sintática nem as camadas abertas:
 *
 * - auto: segue o tema (escuro → "Vácuo", claro → "Papel"), o padrão;
 * - escuro / claro: fundo liso da marca, com grade de pontos (CSS), rios e nomes de lugares;
 * - ruas: OpenStreetMap com ruas, quadras, parques e edificações (tons do tema);
 * - satelite: imagens Esri World Imagery;
 * - topo: OpenTopoMap (curvas de nível e relevo).
 *
 * Os nomes de lugares (LABEL_LAYER) ficam POR CIMA da rede, para continuarem legíveis.
 */
export type BasemapId = "auto" | "escuro" | "claro" | "ruas" | "satelite" | "topo";
export type Tone = "light" | "dark";

export interface Basemap {
  id: BasemapId;
  label: string;
  hint: string;
  /** prévia do seletor (CSS background) */
  swatch: string;
}

export const BASEMAPS: Basemap[] = [
  { id: "auto", label: "Automático", hint: "Segue o tema", swatch: "linear-gradient(135deg, #050607 50%, #F4F6F5 50%)" },
  { id: "escuro", label: "Escuro", hint: "Vácuo da marca", swatch: "radial-gradient(circle, rgba(244,246,245,.35) 1px, transparent 1.4px) 0 0/8px 8px, #07090A" },
  { id: "claro", label: "Claro", hint: "Papel", swatch: "radial-gradient(circle, rgba(15,18,19,.25) 1px, transparent 1.4px) 0 0/8px 8px, #FFFFFF" },
  { id: "ruas", label: "Ruas", hint: "OpenStreetMap", swatch: "linear-gradient(115deg, transparent 46%, #C9CFD1 46% 54%, transparent 54%), linear-gradient(25deg, transparent 47%, #DADFE0 47% 53%, transparent 53%), #EEF0EC" },
  { id: "satelite", label: "Satélite", hint: "Esri World Imagery", swatch: "radial-gradient(circle at 30% 30%, #5E6B45, transparent 55%), radial-gradient(circle at 75% 70%, #8A8A7A, transparent 50%), #2F3A2C" },
  { id: "topo", label: "Topográfico", hint: "OpenTopoMap", swatch: "repeating-radial-gradient(circle at 40% 60%, #E8E4D6 0 4px, #C9B98F 4px 5px), #E8E4D6" },
];

/** Camada de nomes: a rede sintática entra antes dela, para os nomes ficarem legíveis. */
export const LABEL_LAYER = "place-labels";

const OSM = '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a>';
const OMT =
  '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a> · ' +
  OSM;

const ROAD_CLASSES = ["motorway", "trunk", "primary", "secondary", "tertiary", "minor", "service"];

export const basemapStyle: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    openmaptiles: { type: "vector", url: "https://tiles.openfreemap.org/planet", attribution: OMT },
    satelite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "Imagens © Esri, Maxar, Earthstar Geographics",
    },
    topo: {
      type: "raster",
      tiles: ["a", "b", "c"].map((s) => `https://${s}.tile.opentopomap.org/{z}/{x}/{y}.png`),
      tileSize: 256,
      maxzoom: 17,
      attribution: '<a href="https://opentopomap.org" target="_blank" rel="noreferrer">© OpenTopoMap</a> (CC-BY-SA) · SRTM',
    },
  },
  layers: [
    // fundo transparente nos lisos: a cor e a grade de pontos vêm do CSS (.map), como no design
    { id: "background", type: "background", paint: { "background-color": "#07090A", "background-opacity": 0 } },
    { id: "satelite", type: "raster", source: "satelite", layout: { visibility: "none" } },
    { id: "topo", type: "raster", source: "topo", layout: { visibility: "none" }, paint: { "raster-saturation": -0.15 } },
    // "ruas": cobertura do solo, parques, quadras e edificações
    { id: "landuse", type: "fill", source: "openmaptiles", "source-layer": "landuse", layout: { visibility: "none" }, paint: { "fill-color": "#E9ECE6" } },
    { id: "park", type: "fill", source: "openmaptiles", "source-layer": "park", layout: { visibility: "none" }, paint: { "fill-color": "#DDE8D6" } },
    {
      id: "landcover",
      type: "fill",
      source: "openmaptiles",
      "source-layer": "landcover",
      filter: ["in", ["get", "class"], ["literal", ["wood", "grass", "farmland", "wetland"]]],
      layout: { visibility: "none" },
      paint: { "fill-color": "#E1EAD9", "fill-opacity": 0.7 },
    },
    { id: "water", type: "fill", source: "openmaptiles", "source-layer": "water", paint: { "fill-color": "#0D1D24" } },
    {
      id: "waterway",
      type: "line",
      source: "openmaptiles",
      "source-layer": "waterway",
      paint: { "line-color": "#10222B", "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 3] },
    },
    {
      id: "building",
      type: "fill",
      source: "openmaptiles",
      "source-layer": "building",
      minzoom: 14,
      layout: { visibility: "none" },
      paint: { "fill-color": "#DCDFDB", "fill-opacity": ["interpolate", ["linear"], ["zoom"], 14, 0, 15, 0.9] },
    },
    {
      id: "roads",
      type: "line",
      source: "openmaptiles",
      "source-layer": "transportation",
      filter: ["in", ["get", "class"], ["literal", ROAD_CLASSES]],
      layout: { visibility: "none", "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#FFFFFF",
        "line-width": [
          "interpolate",
          ["exponential", 1.5],
          ["zoom"],
          10,
          ["match", ["get", "class"], ["motorway", "trunk", "primary"], 1.6, ["secondary", "tertiary"], 1, 0.4],
          16,
          ["match", ["get", "class"], ["motorway", "trunk", "primary"], 12, ["secondary", "tertiary"], 9, 5],
        ],
      },
    },
    {
      id: LABEL_LAYER,
      type: "symbol",
      source: "openmaptiles",
      "source-layer": "place",
      filter: ["in", ["get", "class"], ["literal", ["city", "town", "village", "suburb"]]],
      layout: {
        "text-field": ["upcase", ["coalesce", ["get", "name:pt"], ["get", "name"]]],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["match", ["get", "class"], ["city", "town"], 13, 11],
        "text-letter-spacing": 0.25,
        "text-max-width": 10,
      },
      paint: {
        "text-color": "rgba(244,246,245,0.72)",
        "text-halo-color": "#07090A",
        "text-halo-width": 1.6,
        "text-halo-blur": 0.5,
      },
    },
  ],
};

/** Mantido para quem ainda importa o nome antigo. */
export const darkBasemapStyle = basemapStyle;

/** Tom do mapa (cores das linhas e rótulos por cima): satélite é escuro, topográfico é claro. */
export function toneOf(id: BasemapId, theme: Tone): Tone {
  if (id === "escuro" || id === "satelite") return "dark";
  if (id === "claro" || id === "topo") return "light";
  return theme; // auto e ruas seguem o tema
}

const PAINT: Record<Tone, { water: string; waterway: string; label: string; halo: string; landuse: string; park: string; landcover: string; building: string; road: string; bg: string }> = {
  dark: {
    water: "#0D1D24",
    waterway: "#10222B",
    label: "rgba(244,246,245,0.72)",
    halo: "#07090A",
    landuse: "#121618",
    park: "#102018",
    landcover: "#0F1914",
    building: "#20272A",
    road: "#353E42",
    bg: "#0B0E0F",
  },
  light: {
    water: "#D6E6EE",
    waterway: "#C4DAE5",
    label: "rgba(15,18,19,0.66)",
    halo: "#FFFFFF",
    landuse: "#EEF0EC",
    park: "#DDE8D6",
    landcover: "#E3EBDB",
    building: "#DCDFDB",
    road: "#FFFFFF",
    bg: "#F4F5F1",
  },
};

/** Liga o fundo escolhido no mapa já carregado; devolve o tom resultante. */
export function applyBasemap(map: MapLibreMap, id: BasemapId, theme: Tone): Tone {
  const tone = toneOf(id, theme);
  const resolved = id === "auto" ? (theme === "dark" ? "escuro" : "claro") : id;
  const p = PAINT[tone];
  const show = (layer: string, on: boolean) => {
    if (map.getLayer(layer)) map.setLayoutProperty(layer, "visibility", on ? "visible" : "none");
  };
  const streets = resolved === "ruas";
  const raster = resolved === "satelite" || resolved === "topo";
  show("satelite", resolved === "satelite");
  show("topo", resolved === "topo");
  for (const layer of ["landuse", "park", "landcover", "building", "roads"]) show(layer, streets);
  show("water", !raster);
  show("waterway", !raster);
  map.setPaintProperty("background", "background-opacity", streets ? 1 : 0);
  map.setPaintProperty("background", "background-color", p.bg);
  map.setPaintProperty("water", "fill-color", p.water);
  map.setPaintProperty("waterway", "line-color", p.waterway);
  map.setPaintProperty("landuse", "fill-color", p.landuse);
  map.setPaintProperty("park", "fill-color", p.park);
  map.setPaintProperty("landcover", "fill-color", p.landcover);
  map.setPaintProperty("building", "fill-color", p.building);
  map.setPaintProperty("roads", "line-color", p.road);
  map.setPaintProperty(LABEL_LAYER, "text-color", resolved === "satelite" ? "#FFFFFF" : p.label);
  map.setPaintProperty(LABEL_LAYER, "text-halo-color", resolved === "satelite" ? "rgba(0,0,0,.75)" : p.halo);
  return tone;
}

const BASEMAP_KEY = "qc-basemap";

export function savedBasemap(): BasemapId {
  try {
    const value = localStorage.getItem(BASEMAP_KEY);
    if (BASEMAPS.some((b) => b.id === value)) return value as BasemapId;
  } catch {
    // armazenamento bloqueado: padrão
  }
  return "auto";
}

export function saveBasemap(id: BasemapId): void {
  try {
    localStorage.setItem(BASEMAP_KEY, id);
  } catch {
    // vale só nesta aba
  }
}
