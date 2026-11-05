import type { Feature, Polygon } from "geojson";
import { useEffect, useRef, useState } from "react";

import type { PolygonProps, PolygonStats } from "../../lib/platformTypes";
import type { Measure, NetworkCollection } from "../../lib/types";
import { SYNTAX_PALETTE } from "../map/syntaxPalette";
import { inRing } from "./geometry";

const LAYERS = [
  { key: "rede", level: "N2", name: "REDE VIÁRIA" },
  { key: "base", level: "N1", name: "TERRITÓRIO" },
] as const;
type LayerKey = (typeof LAYERS)[number]["key"];

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });

interface LayerStackProps {
  polygon: Feature<Polygon, PolygonProps>;
  stats: PolygonStats | undefined;
  measure: Measure;
  network: NetworkCollection;
  onExport: () => void;
  onClose: () => void;
}

function drawTile(
  canvas: HTMLCanvasElement,
  layer: LayerKey,
  polygon: Feature<Polygon, PolygonProps>,
  network: NetworkCollection,
  measure: Measure,
) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = 240 * dpr;
  canvas.height = 240 * dpr;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, 240, 240);
  const ring = polygon.geometry.coordinates[0] ?? [];
  const xs = ring.map((p) => p[0] ?? 0);
  const ys = ring.map((p) => p[1] ?? 0);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const kx = Math.cos((((y0 + y1) / 2) * Math.PI) / 180); // aspecto em lon/lat
  const scale = 200 / Math.max((x1 - x0) * kx, y1 - y0, 1e-9);
  const X = (x: number) => 120 + (x - (x0 + x1) / 2) * kx * scale;
  const Y = (y: number) => 120 - (y - (y0 + y1) / 2) * scale;
  const path = () => {
    g.beginPath();
    ring.forEach(([x = 0, y = 0], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
    g.closePath();
  };
  if (layer === "rede") {
    g.save();
    path();
    g.clip();
    g.lineCap = "round";
    for (const f of network.features) {
      const coords = f.geometry.coordinates;
      const mid = coords[Math.floor(coords.length / 2)] ?? coords[0];
      if (!mid || !inRing(ring, mid[0] ?? 0, mid[1] ?? 0)) continue;
      const cls = f.properties[`c_${measure}_n`];
      g.strokeStyle = typeof cls === "number" ? (SYNTAX_PALETTE[cls] ?? "#4A5155") : "#4A5155";
      g.lineWidth = 0.8 + (typeof cls === "number" ? cls * 0.25 : 0);
      g.beginPath();
      coords.forEach(([x = 0, y = 0], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
      g.stroke();
    }
    g.restore();
    path();
    g.strokeStyle = "rgba(244,246,245,.5)";
    g.lineWidth = 1;
    g.stroke();
  } else {
    path();
    g.fillStyle = "rgba(59,140,255,.18)";
    g.fill();
    g.strokeStyle = "#3B8CFF";
    g.lineWidth = 1.5;
    g.stroke();
    g.fillStyle = "#F4F6F5";
    ring.forEach(([x = 0, y = 0]) => g.fillRect(X(x) - 2, Y(y) - 2, 4, 4));
  }
}

export function LayerStack({ polygon, stats, measure, network, onExport, onClose }: LayerStackProps) {
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState<LayerKey | null>(null);
  const tiles = useRef<Partial<Record<LayerKey, HTMLCanvasElement | null>>>({});

  // o pai monta um LayerStack por polígono (key), então a animação recomeça a cada seleção
  useEffect(() => {
    const t = setTimeout(() => setOpen(true), 80);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    for (const layer of LAYERS) {
      const canvas = tiles.current[layer.key];
      if (canvas) drawTile(canvas, layer.key, polygon, network, measure);
    }
  }, [polygon, network, measure]);

  const ring = polygon.geometry.coordinates[0] ?? [];
  let cx = 0;
  let cy = 0;
  for (const [x = 0, y = 0] of ring) {
    cx += x / ring.length;
    cy += y / ring.length;
  }
  const n = stats?.network.by_radius.n;
  const mean = n?.[measure];
  const classesKm = n?.[`${measure}_classes_km`] ?? [];
  const totalKm = classesKm.reduce((a, b) => a + b, 0) || 1;

  const cards: Record<LayerKey, { metrics: [string, string][]; bar: { w: number; c: string }[] }> = {
    rede: {
      metrics: stats
        ? [
            [stats.network.links.toLocaleString("pt-BR"), "trechos"],
            [`${fmt(stats.network.km, 1)} km`, "de ruas"],
            [
              typeof mean === "number" ? fmt(mean, 3) : "–",
              measure === "nain" ? "integração (NAIN) · n" : "escolha (NACH) · n",
            ],
          ]
        : [["…", "trechos"], ["…", "de ruas"], ["…", "média"]],
      bar: classesKm.map((km, i) => ({ w: km / totalKm, c: SYNTAX_PALETTE[i] ?? "#4A5155" })),
    },
    base: {
      metrics: stats
        ? [
            [`${fmt(stats.territory.area_km2, 2)} km²`, "área"],
            [`${fmt(stats.territory.perimeter_km, 2)} km`, "perímetro"],
            [String(stats.territory.vertices), "vértices"],
          ]
        : [["…", "área"], ["…", "perímetro"], ["…", "vértices"]],
      bar: [],
    },
  };

  const spacing = 140;
  const middle = (LAYERS.length - 1) / 2;

  return (
    <section className="layer-panel" aria-label={`Camadas de ${polygon.properties.name}`}>
      <header className="layer-head">
        <span className="dot-green" aria-hidden="true" />
        <span className="layer-title">{polygon.properties.name}</span>
        <span className="mono muted-2 small">
          {polygon.properties.code} · {fmt(cy, 4)}, {fmt(cx, 4)}
        </span>
        <span className="spacer" />
        <button type="button" className="pill pill-outline pill-sm" onClick={onExport}>
          Exportar GeoJSON
        </button>
        <button type="button" className="icon-circle" onClick={onClose} aria-label="Fechar">
          ×
        </button>
      </header>
      <div className="layer-body">
        <div className="tiles" aria-hidden="true">
          {LAYERS.map((layer, j) => {
            const on = hover === layer.key;
            const dim = hover !== null && !on;
            return (
              <div
                key={layer.key}
                className="tile"
                onMouseEnter={() => setHover(layer.key)}
                onMouseLeave={() => setHover(null)}
                style={{
                  transform: `translateY(${(open ? (j - middle) * spacing : (j - middle) * 6).toFixed(0)}px) rotateX(58deg) rotateZ(-40deg)`,
                  zIndex: 10 - j,
                  opacity: dim ? 0.35 : 1,
                  borderColor: on ? "#2BD46B" : undefined,
                  background: on ? "rgba(43,212,107,.10)" : undefined,
                }}
              >
                <canvas
                  ref={(el) => {
                    tiles.current[layer.key] = el;
                  }}
                />
              </div>
            );
          })}
        </div>
        <div className="layer-cards">
          {LAYERS.map((layer) => {
            const on = hover === layer.key;
            const card = cards[layer.key];
            return (
              <div
                key={layer.key}
                className={on ? "layer-card layer-card-on" : "layer-card"}
                style={{ opacity: open ? (hover && !on ? 0.5 : 1) : 0 }}
                onMouseEnter={() => setHover(layer.key)}
                onMouseLeave={() => setHover(null)}
              >
                <div className="layer-card-head mono">
                  <span style={{ color: on ? "#2BD46B" : layer.key === "base" ? "#3B8CFF" : "#C9CFD1" }}>
                    {layer.level}
                  </span>
                  <span className="muted-2">{layer.name}</span>
                </div>
                <div className="layer-metrics">
                  {card.metrics.map(([v, l]) => (
                    <div key={l}>
                      <span className="metric-v">{v}</span>
                      <span className="metric-l">{l}</span>
                    </div>
                  ))}
                </div>
                {card.bar.length > 0 && (
                  <div className="layer-bar">
                    {card.bar.map((b, i) => (
                      <span key={i} style={{ flex: b.w, background: b.c }} />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
          <p className="muted small layer-note">
            População, relevo e uso do solo entram nas próximas versões (fontes em “Dados”).
          </p>
        </div>
      </div>
    </section>
  );
}
