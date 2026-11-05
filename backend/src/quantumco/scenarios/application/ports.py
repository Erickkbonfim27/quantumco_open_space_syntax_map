from __future__ import annotations

from typing import Protocol
from uuid import UUID

from quantumco.scenarios.domain.workspace import Workspace


class WorkspaceRepository(Protocol):
    def list_for(self, owner_id: UUID) -> list[Workspace]: ...

    def get(self, workspace_id: UUID) -> Workspace | None: ...

    def save(self, workspace: Workspace) -> None:
        """Grava o cenário e substitui seus polígonos (o agregado inteiro)."""
        ...

    def delete(self, workspace_id: UUID) -> None: ...
