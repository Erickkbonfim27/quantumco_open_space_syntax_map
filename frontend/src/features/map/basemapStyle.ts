import type { StyleSpecification } from "maplibre-gl";

/**
 * Mapa de fundo escuro da marca (Quantumco App): quase preto, rios discretos e só os nomes de
 * lugares. Usa os vector tiles do OpenFreeMap (dados OpenStreetMap, esquema OpenMapTiles).
 * Ruas do mapa de fundo ficam de fora: a rede que importa é a nossa.
 */
const TEXT = "rgba(244,246,245,0.72)";

export const darkBasemapStyle: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sources: {
    openmaptiles: {
      type: "vector",
      url: "https://tiles.openfreemap.org/planet",
      attribution:
        '<a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a> · ' +
        '<a href="https://www.openmaptiles.org/" target="_blank" rel="noreferrer">© OpenMapTiles</a> · ' +
        '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">© OpenStreetMap</a>',
    },
  },
  layers: [
    { id: "background", type: "background", paint: { "background-color": "#07090A" } },
    {
      id: "landcover-wood",
      type: "fill",
      source: "openmaptiles",
      "source-layer": "landcover",
      filter: ["==", ["get", "class"], "wood"],
      paint: { "fill-color": "#0B0F0E", "fill-opacity": 0.8 },
    },
    {
      id: "water",
      type: "fill",
      source: "openmaptiles",
      "source-layer": "water",
      paint: { "fill-color": "#0D1D24" },
    },
    {
      id: "waterway",
      type: "line",
      source: "openmaptiles",
      "source-layer": "waterway",
      paint: {
        "line-color": "#10222B",
        "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 3],
      },
    },
    {
      id: "place-labels",
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
        "text-color": TEXT,
        "text-halo-color": "#07090A",
        "text-halo-width": 1.2,
      },
    },
  ],
};
