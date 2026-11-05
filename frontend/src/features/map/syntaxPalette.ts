import type { ExpressionSpecification } from "maplibre-gl";
import type { Measure, RadiusKey } from "../../lib/types";

/**
 * Escala das medidas sintáticas (NAIN/NACH), no espectro dos mapas de Londres:
 * azul = segregado → vermelho = integrado. Cores do design "Quantumco App" (Claude Design);
 * mesma ordem em backend/methodology/v1/symbology.yaml. Classes por percentil ponderado por extensão.
 *
 * Exclusiva das medidas sintáticas: nenhuma outra camada do mapa usa estas cores.
 */
export const SYNTAX_PALETTE = [
  "#2233D6",
  "#1E8FEA",
  "#20C4C4",
  "#4CC64A",
  "#E3DC2E",
  "#F28A1C",
  "#E3231E",
] as const;

/** Classe (0 = mais segregado … 6 = mais integrado) de um percentil entre 0 e 1. */
export function syntaxClass(percentile: number): number {
  const clamped = Math.min(Math.max(percentile, 0), 1);
  return Math.min(SYNTAX_PALETTE.length - 1, Math.floor(clamped * SYNTAX_PALETTE.length));
}



export const RADII: { key: RadiusKey; label: string }[] = [
  { key: "n", label: "n" },
  { key: "2000", label: "2 km" },
  { key: "1200", label: "1,2 km" },
  { key: "800", label: "800 m" },
  { key: "400", label: "400 m" },
];

export const MEASURE_LABEL: Record<Measure, string> = {
  nain: "Integração (NAIN)",
  nach: "Escolha (NACH)",
};

export const classProperty = (measure: Measure, radius: RadiusKey) =>
  `c_${measure}_${radius}` as const;

/** Cor pela classe 0..6; sem classe (entorno) usa o cinza neutro. */
export function syntaxColor(measure: Measure, radius: RadiusKey, fallback: string): ExpressionSpecification {
  const prop = classProperty(measure, radius);
  return [
    "match",
    ["coalesce", ["get", prop], -1],
    ...SYNTAX_PALETTE.flatMap((color, index) => [index, color]),
    fallback,
  ] as unknown as ExpressionSpecification;
}

/** Mais integrado = mais grosso e desenhado por cima (como no design e no depthmapX). */
export function syntaxWidth(measure: Measure, radius: RadiusKey): ExpressionSpecification {
  const base = ["+", 0.6, ["*", 0.32, ["coalesce", ["get", classProperty(measure, radius)], 0]]];
  return [
    "interpolate",
    ["exponential", 1.6],
    ["zoom"],
    10,
    ["*", base, 0.55],
    14,
    ["*", base, 1.6],
    18,
    ["*", base, 5],
  ] as unknown as ExpressionSpecification;
}

export function syntaxSortKey(measure: Measure, radius: RadiusKey): ExpressionSpecification {
  return ["coalesce", ["get", classProperty(measure, radius)], -1] as ExpressionSpecification;
}

/** Cores de MUDANÇA (cenários): fora da escala sintática, para não confundir. */
export const DELTA_COLORS = {
  lossStrong: "#C026D3",
  loss: "#E879F9",
  same: "#3A4246",
  gain: "#86EFAC",
  gainStrong: "#2BD46B",
  removed: "#FF5A5F",
  added: "#F4F6F5",
} as const;

const deltaProperty = (measure: Measure, radius: RadiusKey) => `d_${measure}_${radius}` as const;

export function deltaColor(measure: Measure, radius: RadiusKey): ExpressionSpecification {
  const d = ["coalesce", ["get", deltaProperty(measure, radius)], 0];
  return [
    "case",
    ["==", ["get", "removed"], true],
    DELTA_COLORS.removed,
    ["==", ["get", "new"], true],
    DELTA_COLORS.added,
    ["<=", d, -2],
    DELTA_COLORS.lossStrong,
    ["==", d, -1],
    DELTA_COLORS.loss,
    ["==", d, 1],
    DELTA_COLORS.gain,
    [">=", d, 2],
    DELTA_COLORS.gainStrong,
    DELTA_COLORS.same,
  ] as unknown as ExpressionSpecification;
}

export function deltaWidth(measure: Measure, radius: RadiusKey): ExpressionSpecification {
  const d = ["abs", ["coalesce", ["get", deltaProperty(measure, radius)], 0]];
  const base = [
    "case",
    ["any", ["==", ["get", "removed"], true], ["==", ["get", "new"], true]],
    3.2,
    ["+", 0.7, ["*", 0.9, ["min", d, 3]]],
  ];
  return [
    "interpolate",
    ["exponential", 1.6],
    ["zoom"],
    10,
    ["*", base, 0.55],
    14,
    ["*", base, 1.6],
    18,
    ["*", base, 5],
  ] as unknown as ExpressionSpecification;
}

export function deltaSortKey(measure: Measure, radius: RadiusKey): ExpressionSpecification {
  return [
    "case",
    ["any", ["==", ["get", "removed"], true], ["==", ["get", "new"], true]],
    10,
    ["abs", ["coalesce", ["get", deltaProperty(measure, radius)], 0]],
  ] as unknown as ExpressionSpecification;
}
