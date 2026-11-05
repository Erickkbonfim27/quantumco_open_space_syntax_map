import { config } from "../config";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

type Init = Omit<RequestInit, "body"> & { json?: unknown };

/** Chamada à API com o cookie de sessão (HttpOnly) e mensagens de erro prontas para a tela. */
export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const response = await fetch(`${config.apiUrl}/api/v1/${path}`, {
    credentials: "include",
    ...rest,
    headers: json === undefined ? headers : { "Content-Type": "application/json", ...headers },
    body: json === undefined ? undefined : JSON.stringify(json),
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
