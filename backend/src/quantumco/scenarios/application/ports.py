from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from quantumco.scenarios.domain.network_edits import NetworkEdit
from quantumco.scenarios.domain.run import ScenarioRun
from quantumco.scenarios.domain.workspace import Workspace


class WorkspaceRepository(Protocol):
    def list_for(self, owner_id: UUID) -> list[Workspace]: ...

    def get(self, workspace_id: UUID) -> Workspace | None: ...

    def save(self, workspace: Workspace) -> None:
        """Grava o cenário e substitui seus polígonos e edições (o agregado inteiro)."""
        ...

    def delete(self, workspace_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class RunCounts:
    active_for_user: int  # na fila ou processando, do usuário
    today_for_user: int  # pedidos do usuário desde `since` (exceto cancelados)
    queued_total: int  # na fila, de todos
    running_total: int  # processando agora, de todos


class RunRepository(Protocol):
    def add(self, run: ScenarioRun) -> None: ...

    def save(self, run: ScenarioRun) -> bool:
        """Atualiza o pedido; False se ele não existe mais (cenário apagado no meio)."""
        ...

    def get(self, run_id: UUID) -> ScenarioRun | None: ...

    def latest_for(self, workspace_id: UUID) -> ScenarioRun | None: ...

    def counts(self, owner_id: UUID, since: datetime) -> RunCounts: ...

    def position(self, run: ScenarioRun) -> int:
        """Posição na fila (1 = o próximo a começar)."""
        ...

    def expected_engine_seconds(self, radii: Sequence[str]) -> float | None:
        """Média do tempo do motor nos últimos cálculos concluídos com os mesmos raios."""
        ...

    def queued_ids(self) -> list[UUID]: ...


class QueueUnavailableError(Exception):
    pass


class RunQueue(Protocol):
    def enqueue(self, run_id: UUID) -> None:
        """Põe o pedido na fila; lança QueueUnavailableError se a fila não responde."""
        ...

    def contains(self, run_id: UUID) -> bool: ...

    def workers(self) -> int | None:
        """Processadores ligados consumindo a fila (None se não deu para saber)."""
        ...


class EditRejectedError(Exception):
    """O motor recusou as edições (ex.: ponta longe demais da rede). Mensagem para o usuário."""


class ScenarioEngine(Protocol):
    """Recálculo com as edições nos raios pedidos (implementado pela Análise Sintática)."""

    def run(
        self,
        name: str,
        edits: Sequence[NetworkEdit],
        on_stage: Callable[[str], None],
        radii: Sequence[str],
    ) -> Mapping[str, Any]: ...

    def forget(self, name: str) -> None:
        """Apaga um resultado gravado (cenário apagado durante o cálculo)."""
        ...
