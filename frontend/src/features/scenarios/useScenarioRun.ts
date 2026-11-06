import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "../../lib/api";
import type { ScenarioRun } from "../../lib/platformTypes";
import type { RadiusKey } from "../../lib/types";

const active = (run: ScenarioRun | null) => run?.status === "queued" || run?.status === "running";

/**
 * Pedido de cálculo do cenário: pede, cancela e acompanha (consulta a cada 2–3 s enquanto está
 * na fila ou processando). `offset` corrige a diferença entre o relógio local e o do servidor.
 */
export function useScenarioRun(workspaceId: string) {
  const [run, setRun] = useState<ScenarioRun | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [finishedLive, setFinishedLive] = useState(false);
  const previous = useRef<ScenarioRun | null>(null);

  const accept = useCallback((next: ScenarioRun | null) => {
    if (next) setOffset(Date.parse(next.server_time) - Date.now());
    if (active(previous.current) && next?.status === "done") setFinishedLive(true);
    previous.current = next;
    setRun(next);
  }, []);

  useEffect(() => {
    let alive = true;
    api<ScenarioRun | null>(`workspaces/${workspaceId}/runs/latest`)
      .then((r) => alive && accept(r))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [workspaceId, accept]);

  useEffect(() => {
    if (!run || !active(run)) return;
    const timer = window.setTimeout(
      () => {
        api<ScenarioRun>(`workspaces/${workspaceId}/runs/${run.id}`)
          .then(accept)
          .catch(() => accept({ ...run })); // falha de rede: tenta de novo no próximo ciclo
      },
      run.status === "queued" ? 3000 : 2000,
    );
    return () => window.clearTimeout(timer);
  }, [run, workspaceId, accept]);

  const call = useCallback(
    async (fn: () => Promise<ScenarioRun>) => {
      setBusy(true);
      setError("");
      try {
        accept(await fn());
      } catch (err) {
        setError(err instanceof ApiError ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [accept],
  );

  const request = useCallback(
    (radii: RadiusKey[]) =>
      call(() => api<ScenarioRun>(`workspaces/${workspaceId}/runs`, { method: "POST", json: { radii } })),
    [call, workspaceId],
  );
  const cancel = useCallback(
    () => run && call(() => api<ScenarioRun>(`workspaces/${workspaceId}/runs/${run.id}`, { method: "DELETE" })),
    [call, run, workspaceId],
  );

  return { run, offset, error, busy, request, cancel, active: active(run), finishedLive };
}

/** Relógio que bate a cada segundo enquanto `on` (tempo decorrido na tela). */
export function useTicker(on: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!on) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [on]);
  return now;
}
