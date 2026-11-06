"""Cálculo de um cenário na fila: o pedido, as etapas e o resultado (Q45).

Ciclo: queued → running → done | failed; um pedido ainda na fila pode ser cancelado.
As edições ficam congeladas no pedido: editar o cenário depois não muda um cálculo já pedido.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from quantumco.scenarios.domain.network_edits import NetworkEdit

# Etapas na ordem em que acontecem (a tela traduz). "queued" é a espera na fila.
STAGES = ("queued", "loading", "editing", "engine", "comparing", "saving")


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELED = "canceled"


class InvalidRunTransitionError(RuntimeError):
    pass


class RunRefusedError(Exception):
    """O pedido não pode entrar na fila agora (mensagem pronta para o usuário)."""


@dataclass(slots=True)
class ScenarioRun:
    run_id: UUID
    workspace_id: UUID
    owner_id: UUID
    edits: tuple[NetworkEdit, ...]
    created_at: datetime
    status: RunStatus = RunStatus.QUEUED
    stage: str = "queued"
    # [{"stage": "engine", "at": iso, "seconds": 31.2}] — "seconds" é preenchido ao sair da etapa
    stages: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    attempts: int = 0
    worker: str | None = None
    error: str | None = None
    result: Mapping[str, Any] | None = None

    @classmethod
    def request(
        cls, *, workspace_id: UUID, owner_id: UUID, edits: tuple[NetworkEdit, ...], now: datetime
    ) -> ScenarioRun:
        run = cls(uuid4(), workspace_id, owner_id, edits, now)
        run.stages.append({"stage": "queued", "at": now.isoformat(), "seconds": None})
        return run

    @property
    def active(self) -> bool:
        return self.status in (RunStatus.QUEUED, RunStatus.RUNNING)

    def _require(self, *allowed: RunStatus) -> None:
        if self.status not in allowed:
            raise InvalidRunTransitionError(f"cálculo {self.run_id} está {self.status.value}")

    def _close_stage(self, now: datetime) -> None:
        if self.stages and self.stages[-1]["seconds"] is None:
            began = datetime.fromisoformat(self.stages[-1]["at"])
            self.stages[-1]["seconds"] = round((now - began).total_seconds(), 2)

    def start(self, *, worker: str, now: datetime) -> None:
        self._require(RunStatus.QUEUED)
        self.status = RunStatus.RUNNING
        self.worker = worker
        self.attempts += 1
        self.started_at = now
        self.enter("loading", now)

    def enter(self, stage: str, now: datetime) -> None:
        self._require(RunStatus.RUNNING)
        if stage not in STAGES or stage == "queued":
            raise ValueError(f"etapa desconhecida: {stage}")
        self._close_stage(now)
        self.stage = stage
        self.stages.append({"stage": stage, "at": now.isoformat(), "seconds": None})
        self.heartbeat_at = now

    def finish(self, result: Mapping[str, Any], now: datetime) -> None:
        self._require(RunStatus.RUNNING)
        self._close_stage(now)
        self.status = RunStatus.DONE
        self.stage = "done"
        self.result = dict(result)
        self.finished_at = now
        self.heartbeat_at = now

    def fail(self, message: str, now: datetime) -> None:
        self._require(RunStatus.QUEUED, RunStatus.RUNNING)
        self._close_stage(now)
        self.status = RunStatus.FAILED
        self.error = message
        self.finished_at = now

    def cancel(self, now: datetime) -> None:
        if self.status != RunStatus.QUEUED:
            raise RunRefusedError("Só dá para cancelar um cálculo que ainda está na fila.")
        self._close_stage(now)
        self.status = RunStatus.CANCELED
        self.stage = "canceled"
        self.finished_at = now

    def is_stale(self, now: datetime, after: timedelta) -> bool:
        """Processando, mas sem sinal de vida há tempo demais (worker caiu no meio)."""
        if self.status != RunStatus.RUNNING:
            return False
        last = self.heartbeat_at or self.started_at or self.created_at
        return now - last > after


@dataclass(frozen=True, slots=True)
class RunQuota:
    """Limites da fila (Q45). O dono do site não tem limite diário (testes)."""

    active_per_user: int = 2
    daily_per_user: int = 10
    queue_max: int = 20

    def check(
        self,
        *,
        workspace_active: bool,
        active_for_user: int,
        today_for_user: int,
        queued_total: int,
        unlimited: bool = False,
    ) -> None:
        if workspace_active:
            raise RunRefusedError("Este cenário já está sendo calculado. Aguarde o resultado.")
        if active_for_user >= self.active_per_user:
            raise RunRefusedError(
                f"Você já tem {active_for_user} cálculos em andamento. "
                "Aguarde um terminar para pedir outro."
            )
        if not unlimited and today_for_user >= self.daily_per_user:
            raise RunRefusedError(
                f"Limite de {self.daily_per_user} cálculos por dia atingido. Tente amanhã."
            )
        if queued_total >= self.queue_max:
            raise RunRefusedError("A fila está cheia agora. Tente de novo em alguns minutos.")
