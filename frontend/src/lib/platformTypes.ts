import type {
  Feature,
  FeatureCollection,
  GeometryCollection,
  MultiPolygon,
  Polygon,
} from "geojson";

export interface UserPreferences {
  theme?: "system" | "light" | "dark";
  basemap?: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  organization: string | null;
  initials: string;
  /** foto de perfil (URL com versão); null = mostra as iniciais */
  avatar_url: string | null;
  preferences: UserPreferences;
  created_at: string | null;
  email_verified: boolean;
  /** troca de e-mail aguardando o link de confirmação */
  pending_email: string | null;
}

export type WorkspaceStatus = "rascunho" | "em_analise" | "publicado";
export type WorkspaceMeasure = "nain" | "nach";

export interface PolygonProps {
  id: string;
  code: string;
  name: string;
}

/** Edição da rede num cenário ("e se…"), em lon/lat. */
export type EditType = "remove" | "close" | "add" | "reroute";
export interface NetworkEdit {
  type: EditType;
  link_id?: string;
  coords?: [number, number][];
  label?: string;
}

export interface Workspace {
  id: string;
  name: string;
  measure: WorkspaceMeasure;
  status: WorkspaceStatus;
  polygons: number;
  edits_count: number;
  area: string;
  created_at: string;
  updated_at: string;
  features: Feature<Polygon, PolygonProps>[];
  edits: NetworkEdit[];
}

export type RunStatus = "queued" | "running" | "done" | "failed" | "canceled";
export type RunStage = "queued" | "loading" | "editing" | "engine" | "comparing" | "saving";

export interface RunResult {
  name: string;
  removed: number;
  closed: number;
  added: number;
  engine: string;
  engine_seconds: number;
  snaps_m: number[];
  summary: Record<string, { km_up: number; km_down: number }>;
  preliminary: boolean;
}

/** Cálculo de um cenário na fila (GET /workspaces/{id}/runs/…). */
export interface ScenarioRun {
  id: string;
  status: RunStatus;
  stage: RunStage | "done" | "canceled";
  stages: { stage: RunStage; at: string; seconds: number | null }[];
  edits: number;
  edit_list: NetworkEdit[];
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  attempts: number;
  error: string | null;
  result: RunResult | null;
  queue: { position: number | null; running: number; workers: number | null };
  expected_engine_seconds: number | null;
  server_time: string;
}

export type PolygonCollection = FeatureCollection<Polygon, PolygonProps>;

export interface RadiusStats {
  nain?: number | null;
  nach?: number | null;
  nain_classes_km?: number[];
  nach_classes_km?: number[];
}

export interface PolygonStats {
  territory: { area_km2: number; perimeter_km: number; vertices: number };
  network: { links: number; km: number; by_radius: Record<string, RadiusStats> };
}

export const STATUS_LABEL: Record<WorkspaceStatus, string> = {
  rascunho: "Rascunho",
  em_analise: "Em análise",
  publicado: "Publicado",
};

export const STATUS_COLOR: Record<WorkspaceStatus, string> = {
  rascunho: "#6E777A",
  em_analise: "#2BD46B",
  publicado: "#3B8CFF",
};

export const MEASURE_SHORT: Record<WorkspaceMeasure, string> = {
  nain: "Integração",
  nach: "Escolha",
};

/** Perfil territorial (POST /territory/polygon-profile): IBGE, CNEFE, SGB e CNES. */
export interface GridEntry {
  kind: "continuous" | "categorical";
  cells: number;
  coverage: number | null;
  mean?: number | null;
  min?: number | null;
  max?: number | null;
  p10?: number | null;
  p50?: number | null;
  p90?: number | null;
  shares?: Record<string, number>;
}

export interface TerritoryProfile {
  population: {
    people: number;
    households: number;
    density_km2: number | null;
    unoccupied_share: number | null;
    income_mean: number | null;
    income_heads: number;
    income_tract_range: [number, number] | null;
    tracts: number;
    tracts_income_suppressed: number;
    weighting: ("domicilios" | "area")[];
  };
  streetscape: Record<
    | "paved"
    | "drain"
    | "lighting"
    | "sidewalk"
    | "ramp"
    | "obstacle"
    | "trees"
    | "trees_5"
    | "bus_stop"
    | "bike"
    | "heavy_traffic"
    | "households_surveyed",
    number
  > | null;
  risk: {
    sectors: number;
    worst: string | null;
    area_km2: Record<string, number>;
    processes_km2: Record<string, number>;
    people: number;
    households: number;
  };
  susceptibility: Record<string, Record<string, number>>;
  addresses: {
    total: number;
    by_kind: Record<string, number>;
    non_residential_share: number | null;
    schools: string[];
  };
  health: { total: number; sus: number; by_kind: Record<string, number>; public_units: string[] };
  /** Edificações (Overture); null = camada ainda não importada. */
  buildings?: {
    count: number;
    footprint_m2: number;
    coverage_ratio: number | null;
    with_height_share: number | null;
    mean_height_m: number | null;
    by_source: Record<string, number>;
  } | null;
  /** Camadas da grade de 30 m (relevo, verde, calor, MapBiomas). */
  grid?: Record<string, GridEntry>;
  features: {
    points: [number, number, string][];
    zones: { layer: string; category: string; geometry: Polygon | MultiPolygon | GeometryCollection }[];
    /** amostra de prédios: [lon, lat, área m², do OSM?] */
    buildings?: [number, number, number, boolean][];
  };
  layers: { layer: string; source: string; license: string; rows: number; fetched_at: string }[];
}
