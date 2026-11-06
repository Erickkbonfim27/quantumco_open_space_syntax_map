import { config } from "../config";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

type Init = RequestInit & { json?: unknown };

/** Chamada à API com o cookie de sessão (HttpOnly) e mensagens de erro prontas para a tela. */
export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { json, headers, body: raw, ...rest } = init;
  const response = await fetch(`${config.apiUrl}/api/v1/${path}`, {
    credentials: "include",
    ...rest,
    headers: json === undefined ? headers : { "Content-Type": "application/json", ...headers },
    body: json === undefined ? raw : JSON.stringify(json),
  });
  if (response.status === 204) return undefined as T;
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  if (!response.ok) {
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? "Confira os campos e tente de novo."
          : `Erro ${response.status}`;
    throw new ApiError(message, response.status);
  }
  return body as T;
}

// Dados fixos entre publicações (malha, análise, município): baixados uma vez por sessão do
// navegador e reaproveitados ao trocar de página (o mapa sintático tem ~10 MB).
const cache = new Map<string, Promise<unknown>>();

/** URL absoluta de um recurso da API (ex.: a foto de perfil, que já vem com /api/v1/…). */
export const apiUrl = (path: string) => `${config.apiUrl}${path}`;

export function apiCached<T>(path: string): Promise<T> {
  let request = cache.get(path) as Promise<T> | undefined;
  if (!request) {
    request = api<T>(path);
    cache.set(path, request);
    request.catch(() => cache.delete(path)); // erro não fica em cache
  }
  return request;
}
