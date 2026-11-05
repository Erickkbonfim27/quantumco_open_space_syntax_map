import type { FeatureCollection, LineString, MultiPolygon, Polygon } from "geojson";

export type Zone = "result" | "buffer";

export type Measure = "nain" | "nach";
export type RadiusKey = "n" | "2000" | "1200" | "800" | "400";

type MeasureKey =
  | `${Measure}_${RadiusKey}`
  | `c_${Measure}_${RadiusKey}`
  | `d_${Measure}_${RadiusKey}`;

/** nain_n, nach_800, … (valor) e c_nain_n, … (classe 0..6; null no entorno) */
export type MeasureProperties = { [K in MeasureKey]?: number | null };

export interface LinkProperties extends MeasureProperties {
  link_id: string;
  osm_way_id: number;
  highway: string;
  zone: Zone;
  is_bridge: boolean;
  is_tunnel: boolean;
  length_m: number;
  /** só em cenários */
  removed?: boolean;
  new?: boolean;
}

export interface ScenarioManifest {
  name: string;
  removed: string[];
  added: string[];
  engine_seconds: number;
  created_at: string;
  preliminary: boolean;
  summary_result_zone: Record<string, { km_up: number; km_down: number }>;
}

export interface AnalysisManifest {
  methodology_version: string;
  preliminary: boolean;
  engine: string;
  engine_version: string;
  radii: string[];
  pieces: number;
  created_at: string;
}

export type NetworkCollection = FeatureCollection<LineString, LinkProperties>;
export type MunicipalityCollection = FeatureCollection<Polygon | MultiPolygon, { ibge_code: string }>;

export interface CleaningReport {
  ways_received: number;
  ways_accepted: number;
  rejected_by_reason: Record<string, number>;
  links_total: number;
  links_kept: number;
  links_excluded_disconnected: number;
  component_count: number;
  length_total_m: number;
  length_kept_m: number;
  length_excluded_m: number;
}

export interface Manifest {
  snapshot_id: string;
  methodology_version: string;
  filter_version: string;
  osm_base_timestamp: string;
  source: string;
  created_at: string;
  study_area: { ibge_code: string; osm_relation_id: number; buffer_m: number; crs_epsg: number };
  cleaning_report: CleaningReport;
  license: string;
}

export interface SnapshotData {
  manifest: Manifest;
  network: NetworkCollection;
  municipality: MunicipalityCollection;
  /** null enquanto a análise sintática não rodou (o mapa mostra a rede em tons neutros) */
  analysis: AnalysisManifest | null;
  /** presente quando a URL tem ?cenario=nome */
  scenario: ScenarioManifest | null;
}
