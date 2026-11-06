import type { Feature, Polygon, Position } from "geojson";
import { type CSSProperties, useEffect, useRef, useState, useSyncExternalStore } from "react";

import type { PolygonProps, PolygonStats, TerritoryProfile } from "../../lib/platformTypes";
import type { Measure, NetworkCollection, RadiusKey } from "../../lib/types";
import { cssToken, useTheme } from "../../lib/theme";
import type { Camera, CameraStore } from "../map/cameraStore";
import { SYNTAX_PALETTE } from "../map/syntaxPalette";
import { inRing, tileFrame } from "./geometry";
import { heightOf, loadRelief, paintSlice, type Relief } from "./relief";

/** De cima para baixo, como no design (N1 na base da pilha). Acentos em tokens do tema. */
const LAYERS = [
  { key: "forma", level: "N7", name: "FORMA CONSTRUÍDA", accent: "var(--text-soft)" },
  { key: "risco", level: "N6", name: "RISCO", accent: "var(--danger)" },
  { key: "equip", level: "N5", name: "EQUIPAMENTOS E USO", accent: "var(--green-text)" },
  { key: "entorno", level: "N4", name: "ENTORNO URBANO", accent: "var(--text-soft)" },
  { key: "pop", level: "N3", name: "POPULAÇÃO E RENDA", accent: "var(--ink)" },
  { key: "rede", level: "N2", name: "REDE VIÁRIA", accent: "var(--text-soft)" },
  { key: "base", level: "N1", name: "TERRITÓRIO", accent: "var(--blue-text)" },
] as const;
type LayerKey = (typeof LAYERS)[number]["key"];
type Profile = TerritoryProfile | "erro" | undefined;

// Cores das camadas territoriais: fora da paleta sintática, para não confundir com NAIN/NACH.
// Inundação em azul (#3B8CFF), setor de risco em vermelho-coral (#FF6B5E).
// Tons neutros vêm da tinta do tema (claros no escuro, grafite no claro).
interface Ink {
  fg: (alpha: number) => string;
  soft: (alpha: number) => string;
  muted: (alpha: number) => string;
}

/** O <canvas> não enxerga variáveis CSS: lê os tokens do tema na hora de desenhar. */
function readInk(): Ink {
  const rgba = (rgb: string) => (alpha: number) => `rgba(${rgb},${alpha})`;
  return {
    fg: rgba(cssToken("--fg-rgb", "244, 246, 245")),
    soft: rgba(cssToken("--soft-rgb", "201, 207, 209")),
    muted: rgba(cssToken("--muted-rgb", "155, 163, 166")),
  };
}

type PointStyle = { color: string; size: number; shape: "dot" | "square" | "ring" | "cross" };
const pointStyles = (ink: Ink): Record<string, PointStyle> => ({
  "cnefe:domicilio": { color: ink.fg(0.55), size: 1.4, shape: "dot" },
  "cnefe:domicilio_coletivo": { color: ink.fg(0.55), size: 1.4, shape: "dot" },
  "cnefe:outras_finalidades": { color: ink.muted(0.75), size: 1.6, shape: "dot" },
  "cnefe:ensino": { color: ink.fg(1), size: 4, shape: "square" },
  "cnefe:religioso": { color: ink.muted(1), size: 3, shape: "ring" },
  "cnefe:em_construcao": { color: "#3B8CFF", size: 3, shape: "cross" },
  "cnefe:saude": { color: "#2BD46B", size: 2.4, shape: "dot" },
});
const cnesStyle: PointStyle = { color: "#2BD46B", size: 2.4, shape: "dot" };

/** Pilha parada: inclinação e giro do design. */
const STILL = { tilt: 58, spin: -40 };
// Seguindo o mapa, a pilha copia o *movimento* da câmera a partir da pose do design: com o mapa
// parado (de cima, norte para cima) ela continua na diagonal; girar o mapa gira a pilha igual e
// inclinar o mapa (0–60°) deita a pilha até 78°, onde o relevo aparece de perfil.
const TILT_GAIN = 1 / 3;
const MAX_TILT = 78;
const FOLLOW_KEY = "qc-layer-follow";

function savedFollow(): boolean {
  try {
    return localStorage.getItem(FOLLOW_KEY) === "1";
  } catch {
    return false;
  }
}

function saveFollow(on: boolean): void {
  try {
    localStorage.setItem(FOLLOW_KEY, on ? "1" : "0");
  } catch {
    // vale só nesta aba
  }
}

const noSubscribe = () => () => {};
const noCamera = (): Camera | null => null;

// Maquete do relevo no azul do território: as curvas ficam mais firmes conforme sobem.
const RELIEF_BLUE: [number, number, number] = [59, 140, 255];

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
  radius: RadiusKey;
  network: NetworkCollection;
  /** câmera do mapa principal: com "seguir mapa", a pilha gira e inclina junto */
  camera?: CameraStore;
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
  radius: RadiusKey,
  profile: Profile,
  ink: Ink,
) {
  const g = canvas.getContext("2d");
  if (!g) return;
  const dpr = window.devicePixelRatio || 1;
  canvas.width = 240 * dpr;
  canvas.height = 240 * dpr;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, 240, 240);
  const ring = polygon.geometry.coordinates[0] ?? [];
  const { x: X, y: Y, scale } = tileFrame(ring);
  const trace = (coords: Position[]) =>
    coords.forEach(([x = 0, y = 0], i) => (i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y))));
  const path = () => {
    g.beginPath();
    trace(ring);
    g.closePath();
  };
  const outline = (color = ink.fg(0.5)) => {
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
      const raw = f.properties[`c_${measure}_${radius}`];
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
    g.fillStyle = ink.fg(1);
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
      () => ink.soft(0.55),
      () => 1,
    );
    outline();
    return;
  }
  if (!data) {
    outline(ink.fg(0.25));
    return;
  }
  if (layer === "forma") {
    // cada prédio como um quadrado com a área da pegada (amostra de até 2.500)
    g.save();
    path();
    g.clip();
    const pxPerMeter = scale / 111_320;
    for (const [lon, lat, area, osm] of data.features.buildings ?? []) {
      const side = Math.max(1.2, Math.sqrt(area) * pxPerMeter);
      g.fillStyle = osm ? ink.fg(0.95) : ink.fg(0.62);
      g.fillRect(X(lon) - side / 2, Y(lat) - side / 2, side, side);
    }
    g.restore();
    outline();
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
  const styles = pointStyles(ink);
  for (const [lon, lat, kind] of data.features.points) {
    if (!wanted(kind)) continue;
    const style = styles[kind] ?? (kind.startsWith("cnes:") ? cnesStyle : null);
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

const ML_SOURCES: Record<string, string> = {
  "Google Open Buildings": "rgba(var(--fg-rgb), 0.62)",
  "Microsoft ML Buildings": "rgba(var(--fg-rgb), 0.36)",
  OpenStreetMap: "rgba(var(--fg-rgb), 0.95)",
};

function formCard(b: TerritoryProfile["buildings"]): Card {
  if (!b) {
    return {
      metrics: [["–", "edificações"], ["–", "taxa de ocupação"], ["–", "área construída"]],
      note: "Edificações ainda não importadas neste banco.",
    };
  }
  const total = b.count || 1;
  const machine = (b.by_source["Google Open Buildings"] ?? 0) + (b.by_source["Microsoft ML Buildings"] ?? 0);
  const height =
    b.with_height_share && b.with_height_share >= 0.05 && b.mean_height_m !== null
      ? `Altura média ${fmt(b.mean_height_m, 1)} m (${pct(b.with_height_share)} com altura).`
      : "Altura quase nunca informada: só a pegada no chão.";
  return {
    metrics: [
      [b.count.toLocaleString("pt-BR"), "edificações"],
      [pct(b.coverage_ratio), "taxa de ocupação"],
      [`${b.footprint_m2.toLocaleString("pt-BR")} m²`, "área no chão"],
    ],
    bar: Object.entries(b.by_source).map(([source, n]) => ({
      w: n / total,
      c: ML_SOURCES[source] ?? "rgba(var(--fg-rgb), 0.2)",
    })),
    note: `${pct(machine / total)} detectadas por satélite (Google, Microsoft), ${pct(
      (b.by_source.OpenStreetMap ?? 0) / total,
    )} mapeadas no OSM. ${height} Taxa = pegada ÷ área do polígono (inclui ruas).`,
  };
}

function reliefNote(relief: Relief | "erro" | undefined): string {
  if (relief === undefined) return "Relevo: carregando o modelo de terreno…";
  if (relief === "erro") return "Relevo indisponível: não foi possível baixar o modelo de terreno.";
  const { min, max, step, levels, exaggeration } = relief;
  if (!levels.length) return `Terreno praticamente plano: ${fmt(min, 0)} m de altitude.`;
  return `Relevo: ${fmt(min, 0)} a ${fmt(max, 0)} m de altitude (desnível de ${fmt(max - min, 0)} m). Curvas a cada ${fmt(step, step % 1 ? 1 : 0)} m, escala vertical ${fmt(exaggeration, 1)}×.`;
}

function territoryCards(profile: Profile): Record<"forma" | "risco" | "equip" | "entorno" | "pop", Card> {
  if (profile === undefined || profile === "erro") {
    const v = profile === "erro" ? "indisponível" : "…";
    const blank = (labels: string[]): Card => ({ metrics: labels.map((l) => [v, l]) });
    return {
      forma: blank(["edificações", "taxa de ocupação", "área no chão"]),
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
    forma: formCard(profile.buildings),
    risco: {
      metrics: [
        [String(r.sectors), r.worst ? `setores · ${r.worst.toLowerCase()}` : "setores (SGB)"],
        [r.sectors ? `~${r.people.toLocaleString("pt-BR")}` : "0", "pessoas (est.)"],
        [pct(floodAlta), "inundação alta"],
      ],
      bar: [
        { w: floodAlta, c: "rgba(59,140,255,.9)" },
        { w: floodMedia, c: "rgba(59,140,255,.5)" },
        { w: floodBaixa, c: "rgba(59,140,255,.22)" },
        { w: Math.max(0, 1 - floodAlta - floodMedia - floodBaixa), c: "rgba(var(--fg-rgb), 0.08)" },
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
  radius,
  network,
  camera,
  onClose,
}: LayerStackProps) {
  const [open, setOpen] = useState(false);
  const [hover, setHover] = useState<LayerKey | null>(null);
  const tiles = useRef<Partial<Record<LayerKey, HTMLCanvasElement | null>>>({});
  const slices = useRef<(HTMLCanvasElement | null)[]>([]);
  const [relief, setRelief] = useState<Relief | "erro" | undefined>(undefined);
  const [raised, setRaised] = useState(false);
  // "seguir mapa": a pilha copia a rotação e a inclinação da câmera do mapa principal
  const [follow, setFollow] = useState(savedFollow);
  // terminada a animação longa (abrir, ligar/desligar), a pilha responde rápido à câmera
  const [settled, setSettled] = useState(false);
  const settleTimer = useRef<number | undefined>(undefined);
  const following = follow && camera !== undefined;
  const view = useSyncExternalStore(following ? camera.subscribe : noSubscribe, following ? camera.get : noCamera);

  // o pai monta um LayerStack por polígono (key), então a animação recomeça a cada seleção
  useEffect(() => {
    const t = setTimeout(() => setOpen(true), 80);
    settleTimer.current = window.setTimeout(() => setSettled(true), 950);
    return () => {
      clearTimeout(t);
      window.clearTimeout(settleTimer.current);
    };
  }, []);

  const toggleFollow = () => {
    const next = !follow;
    setFollow(next);
    saveFollow(next);
    setSettled(false);
    window.clearTimeout(settleTimer.current);
    settleTimer.current = window.setTimeout(() => setSettled(true), 850);
  };

  // relevo do polígono (DEM da AWS), uma vez por seleção
  useEffect(() => {
    const ctl = new AbortController();
    loadRelief(polygon.geometry.coordinates[0] ?? [], ctl.signal).then(setRelief, () => {
      if (!ctl.signal.aborted) setRelief("erro");
    });
    return () => ctl.abort();
  }, [polygon]);

  const { theme } = useTheme();
  useEffect(() => {
    // desenha no quadro seguinte: ao trocar o tema, o <html data-theme> só muda no efeito do
    // ThemeProvider, que roda depois deste (a tinta lida agora seria a antiga)
    const frame = requestAnimationFrame(() => {
      const ink = readInk();
      for (const layer of LAYERS) {
        const canvas = tiles.current[layer.key];
        if (canvas) drawTile(canvas, layer.key, polygon, network, measure, radius, profile, ink);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [polygon, network, measure, radius, profile, theme]);

  // fatias da maquete; depois de pintadas, sobem
  useEffect(() => {
    if (!relief || relief === "erro") return;
    const frame = requestAnimationFrame(() => {
      const { size, levels } = relief;
      const buffer = new Uint8ClampedArray(size * size * 4);
      const halfWidth = 0.6 * (size / 240);
      levels.forEach((level, k) => {
        const canvas = slices.current[k];
        const g = canvas?.getContext("2d");
        if (!canvas || !g) return;
        canvas.width = size;
        canvas.height = size;
        const t = levels.length > 1 ? k / (levels.length - 1) : 1;
        paintSlice(buffer, relief, level, RELIEF_BLUE, { line: 0.4 + 0.5 * t, fill: 0.045, halfWidth });
        g.putImageData(new ImageData(buffer, size, size), 0, 0);
      });
      setRaised(true);
    });
    return () => cancelAnimationFrame(frame);
  }, [relief]);

  const ring = polygon.geometry.coordinates[0] ?? [];
  let cx = 0;
  let cy = 0;
  for (const [x = 0, y = 0] of ring) {
    cx += x / ring.length;
    cy += y / ring.length;
  }
  const n = stats?.network.by_radius[radius];
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
              `${measure === "nain" ? "integração (NAIN)" : "escolha (NACH)"} · R ${radius === "n" ? "n" : radius}`,
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
      note: reliefNote(relief),
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

  const tilt = view ? Math.min(MAX_TILT, STILL.tilt + view.pitch * TILT_GAIN) : STILL.tilt;
  const spin = view ? STILL.spin - view.bearing : STILL.spin;
  const spacing = 80; // 7 níveis: um pouco mais juntos que os 92 px de quando eram 6
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
        {camera && (
          <button
            type="button"
            role="switch"
            aria-checked={follow}
            className="toggle layer-follow"
            onClick={toggleFollow}
            title="As camadas giram e inclinam junto com o mapa (Ctrl + arrastar)"
          >
            <span className={follow ? "toggle-track toggle-on" : "toggle-track"}>
              <span className="toggle-knob" />
            </span>
            <span className="mono">Seguir mapa</span>
          </button>
        )}
        <button type="button" className="icon-circle" onClick={onClose} aria-label="Fechar">
          ×
        </button>
      </header>
      <div className="layer-body">
        <div className={following && settled ? "tiles tiles-follow" : "tiles"} aria-hidden="true">
          {LAYERS.map((layer, j) => {
            const on = hover === layer.key;
            const dim = hover !== null && !on;
            // a base guarda a maquete em 3D: opacidade no próprio ladrilho achataria as fatias
            const model = layer.key === "base";
            const style: CSSProperties & { "--dim"?: number } = {
              transform: `translateY(${(open ? (j - middle) * spacing : (j - middle) * 5).toFixed(0)}px) rotateX(${tilt.toFixed(2)}deg) rotateZ(${spin.toFixed(2)}deg)`,
              zIndex: 10 - j,
              opacity: model ? undefined : dim ? 0.3 : 1,
              "--dim": model ? (dim ? 0.3 : 1) : undefined,
              borderColor: on ? layer.accent : undefined,
              background: on ? "rgba(var(--fg-rgb), 0.07)" : undefined,
            };
            return (
              <div
                key={layer.key}
                className={model ? "tile tile-relief" : "tile"}
                onMouseEnter={() => setHover(layer.key)}
                onMouseLeave={() => setHover(null)}
                style={style}
              >
                <canvas
                  ref={(el) => {
                    tiles.current[layer.key] = el;
                  }}
                />
                {model &&
                  relief &&
                  relief !== "erro" &&
                  relief.levels.map((level, k) => (
                    <canvas
                      key={level}
                      className="relief-slice"
                      ref={(el) => {
                        slices.current[k] = el;
                      }}
                      style={{ transform: `translateZ(${raised ? heightOf(relief, level).toFixed(1) : 0}px)` }}
                    />
                  ))}
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
                  <span style={{ color: on ? "var(--green-text)" : layer.accent }}>{layer.level}</span>
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
            suscetibilidade 2013) · CNES · edificações © OpenStreetMap contributors, Overture Maps
            Foundation (ODbL) · relevo SRTM via AWS Terrain Tiles{sources ? ` · importado em ${sources.split("-").reverse().join("/")}` : ""}.
            Dados por setor estimados pela parcela de domicílios do CNEFE dentro do polígono.
          </p>
        </div>
      </div>
    </section>
  );
}
