import { useEffect, useState } from "react";

import { ApiError, apiCached } from "../../lib/api";
import { cityApi } from "../../lib/city";
import type {
  AnalysisManifest,
  Manifest,
  ScenarioManifest,
  MunicipalityCollection,
  NetworkCollection,
  SnapshotData,
} from "../../lib/types";

export type SnapshotState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: SnapshotData };

class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Leitura com cache compartilhado (ver `apiCached`); um pedido já cancelado nem começa. */
async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted();
  try {
    return await apiCached<T>(path);
  } catch (error) {
    if (error instanceof ApiError) throw new HttpError(error.message, error.status);
    throw error;
  }
}

/** Mapa sintático quando a análise existe; senão, só a rede (503 em /syntax). */
async function loadLinks(
  city: string,
  signal: AbortSignal,
): Promise<{ network: NetworkCollection; analysis: AnalysisManifest | null }> {
  try {
    const [analysis, network] = await Promise.all([
      getJson<AnalysisManifest>(cityApi(city, "syntax/manifest"), signal),
      getJson<NetworkCollection>(cityApi(city, "syntax/links"), signal),
    ]);
    return { network, analysis };
  } catch (error) {
    if (error instanceof HttpError && error.status === 503) {
      const network = await getJson<NetworkCollection>(cityApi(city, "network/links"), signal);
      return { network, analysis: null };
    }
    throw error;
  }
}

export const scenarioFromUrl = (): string | null =>
  new URLSearchParams(window.location.search).get("cenario");

async function loadScenario(
  name: string,
  signal: AbortSignal,
): Promise<{ network: NetworkCollection; scenario: ScenarioManifest }> {
  const path = `scenarios/${encodeURIComponent(name)}`;
  const [scenario, network] = await Promise.all([
    getJson<ScenarioManifest>(`${path}/manifest`, signal),
    getJson<NetworkCollection>(`${path}/links`, signal),
  ]);
  return { network, scenario };
}

/** Rede, análise e limite da cidade (`city` = código IBGE; null enquanto a cidade carrega). */
export function useSnapshotData(city: string | null): SnapshotState {
  const [state, setState] = useState<{ city: string | null; value: SnapshotState }>({
    city: null,
    value: { status: "loading" },
  });

  useEffect(() => {
    if (!city) return;
    const controller = new AbortController();
    const scenarioName = scenarioFromUrl();
    Promise.all([
      getJson<Manifest>(cityApi(city, "network/manifest"), controller.signal),
      getJson<MunicipalityCollection>(cityApi(city, "network/municipality"), controller.signal),
      getJson<AnalysisManifest>(cityApi(city, "syntax/manifest"), controller.signal).catch(() => null),
      scenarioName
        ? loadScenario(scenarioName, controller.signal)
        : loadLinks(city, controller.signal).then(({ network }) => ({ network, scenario: null })),
    ])
      .then(([manifest, municipality, analysis, { network, scenario }]) =>
        setState({
          city,
          value: { status: "ready", data: { manifest, network, municipality, analysis, scenario } },
        }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ city, value: { status: "error", message } });
      });
    return () => controller.abort();
  }, [city]);

  // trocou de cidade: até os dados novos chegarem, é "carregando" (nunca a cidade anterior)
  return state.city === city ? state.value : { status: "loading" };
}
