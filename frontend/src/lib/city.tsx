import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router";

import { apiCached } from "./api";

/** Cidade publicada (GET /cities): cada uma é um contexto separado (mapa, camadas, cenários). */
export interface City {
  ibge_code: string;
  name: string;
  uf: string;
  slug: string;
  status: string;
  crs_epsg: number;
  buffer_m: number;
  /** limite municipal: oeste, sul, leste, norte (WGS84) */
  bbox: [number, number, number, number] | null;
  center: [number, number] | null;
  snapshot_id: string | null;
}

/** A primeira cidade do quantumco: padrão quando nada foi escolhido ainda. */
export const DEFAULT_CITY = "4202909";
const KEY = "qc-city";

export const cityPath = (city: City) => `/map/${city.uf.toLowerCase()}/${city.slug}`;
/** Caminho da API de uma cidade: `cities/4208302/network/links`. */
export const cityApi = (code: string, path: string) => `cities/${code}/${path}`;
export const cityLabel = (city: City) => `${city.name}, ${city.uf}`;

export function savedCity(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null; // armazenamento bloqueado
  }
}

export function saveCity(code: string): void {
  try {
    localStorage.setItem(KEY, code);
  } catch {
    // vale só nesta aba
  }
}

/** A cidade escolhida antes (ou Brusque), entre as publicadas. */
export function preferredCity(cities: City[]): City | undefined {
  const saved = savedCity();
  return (
    cities.find((c) => c.ibge_code === saved) ??
    cities.find((c) => c.ibge_code === DEFAULT_CITY) ??
    cities[0]
  );
}

export type CitiesState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; cities: City[] };

export function useCities(): CitiesState {
  const [state, setState] = useState<CitiesState>({ status: "loading" });
  useEffect(() => {
    let alive = true;
    apiCached<City[]>("cities")
      .then((cities) => alive && setState({ status: "ready", cities }))
      .catch((error: unknown) => {
        if (alive) setState({ status: "error", message: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      alive = false;
    };
  }, []);
  return state;
}

/** `/map` sem cidade: abre a última escolhida (ou Brusque). */
export function CityRedirect() {
  const state = useCities();
  if (state.status === "loading") return <div className="center-message">Carregando as cidades…</div>;
  if (state.status === "error") return <div className="center-message">Não foi possível carregar as cidades: {state.message}</div>;
  const city = preferredCity(state.cities);
  if (!city) return <div className="center-message">Nenhuma cidade publicada ainda.</div>;
  return <Navigate to={`${cityPath(city)}${window.location.search}`} replace />;
}

interface CitySelectProps {
  cities: City[];
  value: string;
  /** padrão: abre o mapa da cidade escolhida */
  onChange?: (city: City) => void;
  className?: string;
  label?: string;
  /** só o seletor, sem o rótulo visível (barra do mapa) */
  compact?: boolean;
}

/** Seletor de cidade (o mapa, as camadas e os cenários são sempre de uma cidade). */
export function CitySelect({ cities, value, onChange, className = "", label = "Cidade", compact = false }: CitySelectProps) {
  const navigate = useNavigate();
  return (
    <label className={`city-select ${compact ? "city-select-compact" : ""} ${className}`}>
      {compact ? null : <span className="city-select-label mono">{label}</span>}
      <select
        aria-label={label}
        title={label}
        value={value}
        onChange={(event) => {
          const city = cities.find((c) => c.ibge_code === event.target.value);
          if (!city) return;
          saveCity(city.ibge_code);
          if (onChange) onChange(city);
          else navigate(cityPath(city));
        }}
      >
        {cities.map((c) => (
          <option key={c.ibge_code} value={c.ibge_code}>
            {cityLabel(c)}
          </option>
        ))}
      </select>
    </label>
  );
}
