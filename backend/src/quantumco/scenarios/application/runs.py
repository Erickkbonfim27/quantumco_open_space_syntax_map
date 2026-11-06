"""Casos de uso da fila de cálculo dos cenários (Q45).

API: `ScenarioRuns` pede, acompanha e cancela. Worker: `ExecuteRun` processa um pedido,
gravando cada etapa (com horário) para a tela mostrar o andamento.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from quantumco.scenarios.application.ports import (
    EditRejectedError,
    QueueUnavailableError,
    RunQueue,
    RunRepository,
    ScenarioEngine,
)
from quantumco.scenarios.application.workspaces import WorkspaceNotFoundError, Workspaces
from quantumco.scenarios.domain.run import RunQuota, RunRefusedError, RunStatus, ScenarioRun
from quantumco.shared_kernel.clock import Clock

log = logging.getLogger(__name__)

# Sem sinal de vida por mais que isto, um cálculo "processando" é dado como interrompido.
# Folga sobre o tempo máximo de um cálculo (QC_SCENARIO_TIMEOUT_S, 60 min por padrão): o motor
# leva ~7 min sozinho na cidade inteira e não dá sinal no meio da etapa.
STALE_AFTER = timedelta(minutes=75)
INTERNAL_ERROR = "Erro interno no cálculo. Tente de novo; se repetir, avise o suporte."
INTERRUPTED = "O processamento foi interrompido (o servidor reiniciou). Peça o cálculo de novo."


def result_name(workspace_id: UUID) -> str:
    """Nome do resultado na Análise Sintática: um por cenário (o cálculo novo substitui)."""
    return f"ws-{workspace_id}"


@dataclass(frozen=True, slots=True)
class RunView:
    run: ScenarioRun
    position: int | None  # na fila: 1 = próximo
    running: int  # processando agora (todos os usuários)
    workers: int | None  # processadores ligados
    expected_engine_s: float | None


class ScenarioRuns:
    def __init__(
        self,
        *,
        workspaces: Workspaces,
        runs: RunRepository,
        queue: RunQueue | None,
        clock: Clock,
        quota: RunQuota,
    ) -> None:
        self._workspaces = workspaces
        self._runs = runs
        self._queue = queue
        self._clock = clock
        self._quota = quota

    def request(self, owner_id: UUID, workspace_id: UUID, *, unlimited: bool = False) -> RunView:
        """`unlimited`: sem limite diário (o dono do site, para testes)."""
        workspace = self._workspaces.get(owner_id, workspace_id)
        if not workspace.edits:
            raise RunRefusedError("Adicione pelo menos uma edição na rede antes de calcular.")
        if self._queue is None:
            raise QueueUnavailableError("fila de cálculo não configurada (QC_REDIS_URL)")
        now = self._clock.now()
        latest = self._refresh(self._runs.latest_for(workspace_id))
        counts = self._runs.counts(owner_id, now - timedelta(hours=24))
        self._quota.check(
            workspace_active=bool(latest and latest.active),
            active_for_user=counts.active_for_user,
            today_for_user=counts.today_for_user,
            queued_total=counts.queued_total,
            unlimited=unlimited,
        )
        run = ScenarioRun.request(
            workspace_id=workspace_id, owner_id=owner_id, edits=tuple(workspace.edits), now=now
        )
        self._runs.add(run)
        try:
            self._queue.enqueue(run.run_id)
        except QueueUnavailableError:
            run.fail("A fila de cálculo está fora do ar. Tente de novo em instantes.", now)
            self._runs.save(run)
            raise
        log.info(
            "cálculo %s pedido: cenário %s, %d edições", run.run_id, workspace_id, len(run.edits)
        )
        return self._view(run)

    def latest(self, owner_id: UUID, workspace_id: UUID) -> RunView | None:
        self._workspaces.get(owner_id, workspace_id)
        run = self._refresh(self._runs.latest_for(workspace_id))
        return self._view(run) if run else None

    def view(self, owner_id: UUID, workspace_id: UUID, run_id: UUID) -> RunView:
        return self._view(self._owned_run(owner_id, workspace_id, run_id))

    def cancel(self, owner_id: UUID, workspace_id: UUID, run_id: UUID) -> RunView:
        run = self._owned_run(owner_id, workspace_id, run_id)
        run.cancel(self._clock.now())
        self._runs.save(run)
        log.info("cálculo %s cancelado na fila", run_id)
        return self._view(run)

    def _owned_run(self, owner_id: UUID, workspace_id: UUID, run_id: UUID) -> ScenarioRun:
        self._workspaces.get(owner_id, workspace_id)
        run = self._refresh(self._runs.get(run_id))
        if run is None or run.workspace_id != workspace_id:
            raise WorkspaceNotFoundError("Cálculo não encontrado.")
        return run

    def _refresh(self, run: ScenarioRun | None) -> ScenarioRun | None:
        """Marca como falho um cálculo cujo worker sumiu (ninguém mais vai terminá-lo)."""
        if run is not None and run.is_stale(self._clock.now(), STALE_AFTER):
            run.fail(INTERRUPTED, self._clock.now())
            self._runs.save(run)
            log.warning("cálculo %s sem sinal do worker: marcado como interrompido", run.run_id)
        return run

    def _view(self, run: ScenarioRun) -> RunView:
        counts = self._runs.counts(run.owner_id, run.created_at)
        position = self._runs.position(run) if run.status == RunStatus.QUEUED else None
        workers = self._queue.workers() if self._queue and run.active else None
        return RunView(
            run=run,
            position=position,
            running=counts.running_total,
            workers=workers,
            expected_engine_s=self._runs.expected_engine_seconds() if run.active else None,
        )


class ExecuteRun:
    """Processa um pedido da fila (roda dentro do worker)."""

    def __init__(
        self, *, runs: RunRepository, engine: ScenarioEngine, clock: Clock, worker: str
    ) -> None:
        self._runs = runs
        self._engine = engine
        self._clock = clock
        self._worker = worker

    def __call__(self, run_id: UUID) -> RunStatus | None:
        run = self._runs.get(run_id)
        if run is None:
            log.info("cálculo %s não existe mais (cenário apagado); ignorado", run_id)
            return None
        if run.status != RunStatus.QUEUED:
            log.info("cálculo %s está %s; nada a fazer", run_id, run.status.value)
            return run.status
        started = time.perf_counter()
        waited = (self._clock.now() - run.created_at).total_seconds()
        run.start(worker=self._worker, now=self._clock.now())
        self._runs.save(run)
        log.info(
            "cálculo %s: início (tentativa %d, %.1fs na fila, %d edições, worker %s)",
            run_id,
            run.attempts,
            waited,
            len(run.edits),
            self._worker,
        )
        last_stage, last_t = run.stage, time.perf_counter()

        def on_stage(stage: str) -> None:
            nonlocal last_stage, last_t
            if stage == last_stage:
                return
            now = time.perf_counter()
            log.info("cálculo %s: %s ok em %.1fs → %s", run_id, last_stage, now - last_t, stage)
            last_stage, last_t = stage, now
            run.enter(stage, self._clock.now())
            if not self._runs.save(run):
                raise _RunGoneError

        name = result_name(run.workspace_id)
        try:
            outcome = self._engine.run(name, run.edits, on_stage)
        except _RunGoneError:
            log.info("cálculo %s: cenário apagado durante o cálculo; abandonado", run_id)
            self._engine.forget(name)
            return None
        except EditRejectedError as error:
            run.fail(str(error), self._clock.now())
            self._runs.save(run)
            log.info("cálculo %s recusado pelo motor: %s", run_id, error)
            return run.status
        except Exception:
            log.exception(
                "cálculo %s falhou depois de %.1fs", run_id, time.perf_counter() - started
            )
            run.fail(INTERNAL_ERROR, self._clock.now())
            self._runs.save(run)
            raise
        run.finish(outcome, self._clock.now())
        if not self._runs.save(run):
            self._engine.forget(name)
            return None
        log.info("cálculo %s concluído em %.1fs", run_id, time.perf_counter() - started)
        return run.status


class _RunGoneError(Exception):
    """O pedido sumiu do banco no meio do cálculo."""
