import type { ExpressionSpecification } from "maplibre-gl";

/**
 * Agrupamento das classes OSM na hierarquia da LC 419/2024 (methodology/v1/widths.csv).
 *
 * Cores NEUTRAS de propósito: a escala de cor (azul → vermelho) é reservada às medidas
 * sintáticas (NAIN/NACH), seguindo o padrão do Depthmap. A classe da via não é medida
 * sintática e não pode usar essa escala.
 */
export interface HighwayGroup {
  key: string;
  label: string;
  classes: readonly string[];
  color: string;
  /** largura base em px no zoom 14 */
  width: number;
}

export const HIGHWAY_GROUPS: readonly HighwayGroup[] = [
  {
    key: "estrutural",
    label: "Estrutural",
    classes: ["motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link"],
    color: "#E4E8E7",
    width: 3.4,
  },
  {
    key: "arterial",
    label: "Arterial",
    classes: ["secondary", "secondary_link"],
    color: "#C9CFD1",
    width: 2.8,
  },
  {
    key: "coletora",
    label: "Coletora",
    classes: ["tertiary", "tertiary_link"],
    color: "#AEB5B8",
    width: 2.2,
  },
  {
    key: "local",
    label: "Local",
    classes: ["residential", "unclassified", "road", "living_street"],
    color: "#8A9396",
    width: 1.3,
  },
  { key: "servico", label: "Serviço", classes: ["service"], color: "#5C6467", width: 0.9 },
  {
    key: "pedestre",
    label: "Pedestre e escadaria",
    classes: ["pedestrian", "steps"],
    color: "#7A8386",
    width: 1.2,
  },
  { key: "rural", label: "Estrada rural (só no entorno)", classes: ["track"], color: "#4A5155", width: 0.9 },
];

const FALLBACK_COLOR = "#6E777A";
const FALLBACK_WIDTH = 1;

export function groupFor(highway: string): HighwayGroup | undefined {
  return HIGHWAY_GROUPS.find((group) => group.classes.includes(highway));
}

function matchByClass(pick: (group: HighwayGroup) => string | number, fallback: string | number) {
  const pairs = HIGHWAY_GROUPS.flatMap((group) => [[...group.classes], pick(group)]);
  return ["match", ["get", "highway"], ...pairs, fallback] as unknown as ExpressionSpecification;
}

export const lineColor = (): ExpressionSpecification => matchByClass((g) => g.color, FALLBACK_COLOR);

/** Largura cresce com o zoom; a base vem da hierarquia da via. */
export const lineWidth = (scale = 1): ExpressionSpecification => {
  const base = matchByClass((g) => g.width * scale, FALLBACK_WIDTH * scale);
  return [
    "interpolate",
    ["exponential", 1.6],
    ["zoom"],
    10,
    ["*", base, 0.35],
    14,
    base,
    18,
    ["*", base, 4],
  ] as ExpressionSpecification;
};

/** Q14: Brusque com opacidade cheia; o entorno (buffer) esmaecido. */
export const BUFFER_OPACITY = 0.28;
export const lineOpacity = (): ExpressionSpecification =>
  ["case", ["==", ["get", "zone"], "buffer"], BUFFER_OPACITY, 0.95] as ExpressionSpecification;
