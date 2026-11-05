import type { Feature, Polygon, Position } from "geojson";
import { useEffect, useRef, useState } from "react";

import type { PolygonProps, PolygonStats, TerritoryProfile } from "../../lib/platformTypes";
import type { Measure, NetworkCollection } from "../../lib/types";
import { SYNTAX_PALETTE } from "../map/syntaxPalette";
import { inRing } from "./geometry";

/** De cima para baixo, como no design (N1 na base da pilha). */
const LAYERS = [
  { key: "risco", level: "N6", name: "RISCO", accent: "#FF6B5E" },
  { key: "equip", level: "N5", name: "EQUIPAMENTOS E USO", accent: "#2BD46B" },
  { key: "entorno", level: "N4", name: "ENTORNO URBANO", accent: "#C9CFD1" },
  { key: "pop", level: "N3", name: "POPULAÇÃO E RENDA", accent: "#F4F6F5" },
  { key: "rede", level: "N2", name: "REDE VIÁRIA", accent: "#C9CFD1" },
  { key: "base", level: "N1", name: "TERRITÓRIO", accent: "#3B8CFF" },
] as const;
type LayerKey = (typeof LAYERS)[number]["key"];
type Profile = TerritoryProfile | "erro" | undefined;

// Cores das camadas territoriais: fora da paleta sintática, para não confundir com NAIN/NACH.
// Inundação em azul (#3B8CFF), setor de risco em vermelho-coral (#FF6B5E).
const POINT_STYLE: Record<string, { color: string; size: number; shape: "dot" | "square" | "ring" | "cross" }> = {
  "cnefe:domicilio": { color: "rgba(244,246,245,.55)", size: 1.4, shape: "dot" },
  "cnefe:domicilio_coletivo": { color: "rgba(244,246,245,.55)", size: 1.4, shape: "dot" },
  "cnefe:outras_finalidades": { color: "rgba(155,163,166,.75)", size: 1.6, shape: "dot" },
  "cnefe:ensino": { color: "#F4F6F5", size: 4, shape: "square" },
  "cnefe:religioso": { color: "#9BA3A6", size: 3, shape: "ring" },
  "cnefe:em_construcao": { color: "#3B8CFF", size: 3, shape: "cross" },
  "cnefe:saude": { color: "#2BD46B", size: 2.4, shape: "dot" },
};
const cnesStyle = { color: "#2BD46B", size: 2.4, shape: "dot" } as const;

const fmt = (v: number, d: number) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v: number | null | undefined) => (typeof v === "number" ? `${fmt(v * 100, 0)}%` : "–");
const brl = (v: number | null | undefined) =>
  typeof v === "number" ? `R$ ${v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}` : "–";

interface LayerStackProps {
  polygon: Feature<Polygon, PolygonProps>;
  stats: PolygonStats | undefined;
  profile: Profile;
  measure: Measure;
  network: NetworkCollection;
  onExport: () => void;
  onClose: () => void;
}

interface Card {
  metrics: [string, string][];
  bar?: { w: number; c: string }[];
  note?: string;
}

function drawTile(
  canvas: HTMLCanvasElement,
  layer: LayerKey,
  polygon: Feature<Polygon, PolygonProps>,
  network: NetworkCollection,
  measure: Measure,
  profile: Profile,
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
  const trace = (coords: Position[]) =>
    coords.forEach(([x = 0, y = 0], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
  const path = () => {
    g.beginPath();
    trace(ring);
    g.closePath();
  };
  const outline = (color = "rgba(244,246,245,.5)") => {
    path();
    g.strokeStyle = color;
    g.lineWidth = 1;
    g.stroke();
  };
  const streets = (color: (cls: number | null) => string, width: (cls: number | null) => number) => {
    g.save();
    path();
    g.clip();
    g.lineCap = "round";
    for (const f of network.features) {
      const coords = f.geometry.coordinates;
      const mid = coords[Math.floor(coords.length / 2)] ?? coords[0];
      if (!mid || !inRing(ring, mid[0] ?? 0, mid[1] ?? 0)) continue;
      const raw = f.properties[`c_${measure}_n`];
      const cls = typeof raw === "number" ? raw : null;
      g.strokeStyle = color(cls);
      g.lineWidth = width(cls);
      g.beginPath();
      trace(coords);
      g.stroke();
    }
    g.restore();
  };
  const data = profile && profile !== "erro" ? profile : null;

  if (layer === "base") {
    path();
    g.fillStyle = "rgba(59,140,255,.18)";
    g.fill();
    g.strokeStyle = "#3B8CFF";
    g.lineWidth = 1.5;
    g.stroke();
    g.fillStyle = "#F4F6F5";
    ring.forEach(([x = 0, y = 0]) => g.fillRect(X(x) - 2, Y(y) - 2, 4, 4));
    return;
  }
  if (layer === "rede") {
    streets(
      (cls) => (cls === null ? "#4A5155" : (SYNTAX_PALETTE[cls] ?? "#4A5155")),
      (cls) => 0.8 + (cls ?? 0) * 0.25,
    );
    outline();
    return;
  }
  if (layer === "entorno") {
    streets(
      () => "rgba(201,207,209,.55)",
      () => 1,
    );
    outline();
    return;
  }
  if (!data) {
    outline("rgba(244,246,245,.25)");
    return;
  }
  if (layer === "risco") {
    g.save();
    path();
    g.clip();
    for (const zone of data.features.zones) {
      const polys =
        zone.geometry.type === "Polygon"
          ? [zone.geometry.coordinates]
          : zone.geometry.type === "MultiPolygon"
            ? zone.geometry.coordinates
            : [];
      const flood = zone.layer === "suscet_inundacao";
      g.fillStyle = flood
        ? zone.category === "Alta"
          ? "rgba(59,140,255,.42)"
          : "rgba(59,140,255,.2)"
        : "rgba(255,107,94,.55)";
      for (const poly of polys) {
        g.beginPath();
        poly.forEach((r) => {
          trace(r);
          g.closePath();
        });
        g.fill("evenodd");
      }
    }
    g.restore();
    outline();
    return;
  }
  // população (domicílios) e equipamentos (o resto): pontos do CNEFE/CNES
  const wanted = (kind: string) =>
    layer === "pop"
      ? kind.startsWith("cnefe:domicilio")
      : !kind.startsWith("cnefe:domicilio");
  for (const [lon, lat, kind] of data.features.points) {
    if (!wanted(kind)) continue;
    const style = POINT_STYLE[kind] ?? (kind.startsWith("cnes:") ? cnesStyle : null);
    if (!style) continue;
    const [px, py] = [X(lon), Y(lat)];
    g.fillStyle = style.color;
    g.strokeStyle = style.color;
    g.lineWidth = 1;
    if (style.shape === "square") g.fillRect(px - style.size / 2, py - style.size / 2, style.size, style.size);
    else if (style.shape === "ring") {
      g.beginPath();
      g.arc(px, py, style.size, 0, 7);
      g.stroke();
    } else if (style.shape === "cross") {
      g.beginPath();
      g.moveTo(px - style.size, py);
      g.lineTo(px + style.size, py);
      g.moveTo(px, py - style.size);
      g.lineTo(px, py + style.size);
      g.stroke();
    } else {
      g.beginPath();
      g.arc(px, py, style.size, 0, 7);
      g.fill();
    }
  }
  outline();
}

function territoryCards(profile: Profile): Record<"risco" | "equip" | "entorno" | "pop", Card> {
  if (profile === undefined || profile === "erro") {
    const v = profile === "erro" ? "indisponível" : "…";
    const blank = (labels: string[]): Card => ({ metrics: labels.map((l) => [v, l]) });
    return {
      risco: blank(["setores (SGB)", "pessoas (est.)", "inundação alta"]),
      equip: blank(["escolas", "saúde (CNES)", "não residencial"]),
      entorno: blank(["com calçada", "iluminação", "arborização"]),
      pop: blank(["habitantes", "hab/km²", "renda média"]),
    };
  }
  const { population: p, streetscape: s, risk: r, susceptibility, addresses: a, health: h } = profile;
  const flood = susceptibility.suscet_inundacao ?? {};
  const floodAlta = flood.Alta ?? 0;
  const floodMedia = flood["Média"] ?? 0;
  const floodBaixa = flood.Baixa ?? 0;
  const slide = susceptibility.suscet_movimento_de_massa?.Alta ?? 0;
  const school = a.by_kind.ensino ?? 0;
  return {
    risco: {
      metrics: [
        [r.sectors ? `${r.sectors} · ${r.worst ?? ""}` : "nenhum", "setores (SGB)"],
        [r.sectors ? `~${r.people.toLocaleString("pt-BR")}` : "0", "pessoas (est.)"],
        [pct(floodAlta), "inundação alta"],
      ],
      bar: [
        { w: floodAlta, c: "rgba(59,140,255,.9)" },
        { w: floodMedia, c: "rgba(59,140,255,.5)" },
        { w: floodBaixa, c: "rgba(59,140,255,.22)" },
        { w: Math.max(0, 1 - floodAlta - floodMedia - floodBaixa), c: "rgba(244,246,245,.08)" },
      ],
      note: `Suscetibilidade alta a deslizamento: ${pct(slide)} da área.${
        Object.keys(r.processes_km2).length
          ? ` Risco mapeado: ${Object.keys(r.processes_km2).join(", ").toLowerCase()}.`
          : ""
      }`,
    },
    equip: {
      metrics: [
        [String(school), "escolas (CNEFE)"],
        [`${h.total}`, `saúde · ${h.sus} SUS`],
        [pct(a.non_residential_share), "não residencial"],
      ],
      note:
        [
          a.by_kind.em_construcao ? `${a.by_kind.em_construcao} obras em andamento (2022)` : "",
          a.by_kind.religioso ? `${a.by_kind.religioso} templos` : "",
          h.public_units.length ? `Unidades: ${h.public_units.slice(0, 3).join(", ")}` : "",
        ]
          .filter(Boolean)
          .join(" · ") || undefined,
    },
    entorno: s
      ? {
          metrics: [
            [pct(s.sidewalk), "com calçada"],
            [pct(s.lighting), "iluminação"],
            [pct(s.trees), "arborização"],
          ],
          note: `Rampa ${pct(s.ramp)} · ponto de ônibus ${pct(s.bus_stop)} · ciclovia ${pct(s.bike)} · obstáculo na calçada ${pct(s.obstacle)} (domicílios por face de quadra).`,
        }
      : { metrics: [["–", "fora da pesquisa"], ["–", ""], ["–", ""]], note: "O IBGE só pesquisou o entorno em setores urbanos." },
    pop: {
      metrics: [
        [p.people.toLocaleString("pt-BR"), "habitantes"],
        [p.density_km2 === null ? "–" : fmt(p.density_km2, 0), "hab/km²"],
        [brl(p.income_mean), "renda média"],
      ],
      note: `Estimativa: ${p.households.toLocaleString("pt-BR")} domicílios ocupados · ${pct(p.unoccupied_share)} não ocupados · ${p.tracts} setores${
        p.tracts_income_suppressed ? ` (${p.tracts_income_suppressed} com renda sigilosa)` : ""
      }`,
    },
  };
}

export function LayerStack({
  polygon,
  stats,
  profile,
  measure,
  network,
  onExport,
  onClose,
}: LayerStackProps) {
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
      if (canvas) drawTile(canvas, layer.key, polygon, network, measure, profile);
    }
  }, [polygon, network, measure, profile]);

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

  const cards: Record<LayerKey, Card> = {
    ...territoryCards(profile),
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
        : [
            ["…", "trechos"],
            ["…", "de ruas"],
            ["…", "média"],
          ],
      bar: classesKm.map((km, i) => ({ w: km / totalKm, c: SYNTAX_PALETTE[i] ?? "#4A5155" })),
    },
    base: {
      metrics: stats
        ? [
            [`${fmt(stats.territory.area_km2, 2)} km²`, "área"],
            [`${fmt(stats.territory.perimeter_km, 2)} km`, "perímetro"],
            [String(stats.territory.vertices), "vértices"],
          ]
        : [
            ["…", "área"],
            ["…", "perímetro"],
            ["…", "vértices"],
          ],
    },
  };

  const spacing = 92;
  const middle = (LAYERS.length - 1) / 2;
  const sources =
    profile && profile !== "erro"
      ? [...new Set(profile.layers.map((l) => l.fetched_at.slice(0, 10)))].sort().at(-1)
      : null;

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
                  transform: `translateY(${(open ? (j - middle) * spacing : (j - middle) * 5).toFixed(0)}px) rotateX(58deg) rotateZ(-40deg)`,
                  zIndex: 10 - j,
                  opacity: dim ? 0.3 : 1,
                  borderColor: on ? layer.accent : undefined,
                  background: on ? "rgba(244,246,245,.07)" : undefined,
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
                  <span style={{ color: on ? "#2BD46B" : layer.accent }}>{layer.level}</span>
                  <span className="muted-2">{layer.name}</span>
                </div>
                <div className="layer-metrics">
                  {card.metrics.map(([v, l], i) => (
                    <div key={`${l}-${i}`}>
                      <span className="metric-v">{v}</span>
                      <span className="metric-l">{l}</span>
                    </div>
                  ))}
                </div>
                {card.bar && card.bar.length > 0 && (
                  <div className="layer-bar">
                    {card.bar.map((b, i) => (
                      <span key={i} style={{ flex: b.w, background: b.c }} />
                    ))}
                  </div>
                )}
                {card.note && <p className="layer-card-note">{card.note}</p>}
              </div>
            );
          })}
          <p className="muted small layer-note">
            Fontes: IBGE Censo 2022 (setores, renda, entorno, CNEFE) · SGB (risco 2018–19,
            suscetibilidade 2013) · CNES{sources ? ` · importado em ${sources.split("-").reverse().join("/")}` : ""}.
            Dados por setor estimados pela parcela de domicílios do CNEFE dentro do polígono.
          </p>
        </div>
      </div>
    </section>
  );
}
