import type {
  Feature,
  FeatureCollection,
  GeometryCollection,
  MultiPolygon,
  Polygon,
} from "geojson";

export interface User {
  id: string;
  name: string;
  email: string;
  organization: string | null;
  initials: string;
}

export type WorkspaceStatus = "rascunho" | "em_analise" | "publicado";
export type WorkspaceMeasure = "nain" | "nach";

export interface PolygonProps {
  id: string;
  code: string;
  name: string;
}

export interface Workspace {
  id: string;
  name: string;
  measure: WorkspaceMeasure;
  status: WorkspaceStatus;
  polygons: number;
  area: string;
  created_at: string;
  updated_at: string;
  features: Feature<Polygon, PolygonProps>[];
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
  features: {
    points: [number, number, string][];
    zones: { layer: string; category: string; geometry: Polygon | MultiPolygon | GeometryCollection }[];
  };
  layers: { layer: string; source: string; license: string; rows: number; fetched_at: string }[];
}
