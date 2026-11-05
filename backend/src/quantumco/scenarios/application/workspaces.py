"""Casos de uso dos cenários do usuário. Todo acesso confere o dono."""

from __future__ import annotations

from uuid import UUID

from quantumco.scenarios.application.ports import WorkspaceRepository
from quantumco.scenarios.domain.workspace import (
    AreaPolygon,
    Measure,
    Ring,
    Status,
    Workspace,
)
from quantumco.shared_kernel.clock import Clock


class WorkspaceNotFoundError(LookupError):
    pass


class Workspaces:
    def __init__(self, *, repository: WorkspaceRepository, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    def _owned(self, owner_id: UUID, workspace_id: UUID) -> Workspace:
        workspace = self._repo.get(workspace_id)
        # cenário de outro usuário responde como inexistente (não revela que existe)
        if workspace is None or workspace.owner_id != owner_id:
            raise WorkspaceNotFoundError("Cenário não encontrado.")
        return workspace

    def list(self, owner_id: UUID) -> list[Workspace]:
        return self._repo.list_for(owner_id)

    def create(self, owner_id: UUID, *, name: str, measure: Measure) -> Workspace:
        workspace = Workspace.create(
            owner_id=owner_id, name=name, measure=measure, now=self._clock.now()
        )
        self._repo.save(workspace)
        return workspace

    def get(self, owner_id: UUID, workspace_id: UUID) -> Workspace:
        return self._owned(owner_id, workspace_id)

    def update(
        self,
        owner_id: UUID,
        workspace_id: UUID,
        *,
        name: str | None = None,
        measure: Measure | None = None,
        status: Status | None = None,
    ) -> Workspace:
        workspace = self._owned(owner_id, workspace_id)
        workspace.update(name=name, measure=measure, status=status, now=self._clock.now())
        self._repo.save(workspace)
        return workspace

    def delete(self, owner_id: UUID, workspace_id: UUID) -> None:
        self._owned(owner_id, workspace_id)
        self._repo.delete(workspace_id)

    def add_polygon(
        self, owner_id: UUID, workspace_id: UUID, *, name: str | None, ring: Ring
    ) -> AreaPolygon:
        workspace = self._owned(owner_id, workspace_id)
        polygon = workspace.add_polygon(name=name, ring=ring, now=self._clock.now())
        self._repo.save(workspace)
        return polygon

    def remove_polygon(self, owner_id: UUID, workspace_id: UUID, polygon_id: UUID) -> None:
        workspace = self._owned(owner_id, workspace_id)
        workspace.remove_polygon(polygon_id, self._clock.now())
        self._repo.save(workspace)
