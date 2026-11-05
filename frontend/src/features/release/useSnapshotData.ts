import { useEffect, useState } from "react";

import { config } from "../../config";
import type {
  AnalysisManifest,
  Manifest,
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

async function getJson<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(`${config.apiUrl}/api/v1/${path}`, { signal });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new HttpError(body?.detail ?? `${path}: HTTP ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

/** Mapa sintático quando a análise existe; senão, só a rede (503 em /syntax). */
async function loadLinks(
  signal: AbortSignal,
): Promise<{ network: NetworkCollection; analysis: AnalysisManifest | null }> {
  try {
    const [analysis, network] = await Promise.all([
      getJson<AnalysisManifest>("syntax/manifest", signal),
      getJson<NetworkCollection>("syntax/links", signal),
    ]);
    return { network, analysis };
  } catch (error) {
    if (error instanceof HttpError && error.status === 503) {
      return { network: await getJson<NetworkCollection>("network/links", signal), analysis: null };
    }
    throw error;
  }
}

export function useSnapshotData(): SnapshotState {
  const [state, setState] = useState<SnapshotState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      getJson<Manifest>("network/manifest", controller.signal),
      getJson<MunicipalityCollection>("network/municipality", controller.signal),
      loadLinks(controller.signal),
    ])
      .then(([manifest, municipality, { network, analysis }]) =>
        setState({ status: "ready", data: { manifest, network, municipality, analysis } }),
      )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const message = error instanceof Error ? error.message : String(error);
        setState({ status: "error", message });
      });
    return () => controller.abort();
  }, []);

  return state;
}
