import type { Feature, FeatureCollection, Polygon } from "geojson";

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
