"""Casos de uso dos cenários do usuário. Todo acesso confere o dono."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from quantumco.scenarios.application.ports import CityAreas, WorkspaceRepository
from quantumco.scenarios.domain.common import CityArea, InvalidWorkspaceError
from quantumco.scenarios.domain.network_edits import NetworkEdit
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
    def __init__(self, *, repository: WorkspaceRepository, clock: Clock, cities: CityAreas) -> None:
        self._repo = repository
        self._clock = clock
        self._cities = cities

    def _area(self, ibge_code: str) -> CityArea:
        area = self._cities.area(ibge_code)
        if area is None:
            raise InvalidWorkspaceError("Essa cidade ainda não está disponível.")
        return area

    def _owned(self, owner_id: UUID, workspace_id: UUID) -> Workspace:
        workspace = self._repo.get(workspace_id)
        # cenário de outro usuário responde como inexistente (não revela que existe)
        if workspace is None or workspace.owner_id != owner_id:
            raise WorkspaceNotFoundError("Cenário não encontrado.")
        return workspace

    def list(self, owner_id: UUID) -> list[Workspace]:
        return self._repo.list_for(owner_id)

    def create(self, owner_id: UUID, *, ibge_code: str, name: str, measure: Measure) -> Workspace:
        workspace = Workspace.create(
            owner_id=owner_id,
            area=self._area(ibge_code),
            name=name,
            measure=measure,
            now=self._clock.now(),
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
        polygon = workspace.add_polygon(
            name=name, ring=ring, area=self._area(workspace.ibge_code), now=self._clock.now()
        )
        self._repo.save(workspace)
        return polygon

    def set_edits(
        self, owner_id: UUID, workspace_id: UUID, edits: Sequence[NetworkEdit]
    ) -> Workspace:
        workspace = self._owned(owner_id, workspace_id)
        workspace.set_edits(edits, self._area(workspace.ibge_code), self._clock.now())
        self._repo.save(workspace)
        return workspace

    def remove_polygon(self, owner_id: UUID, workspace_id: UUID, polygon_id: UUID) -> None:
        workspace = self._owned(owner_id, workspace_id)
        workspace.remove_polygon(polygon_id, self._clock.now())
        self._repo.save(workspace)
