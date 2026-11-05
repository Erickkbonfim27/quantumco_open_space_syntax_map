"""Implementações em memória das portas, para testar a API sem banco."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from copy import deepcopy
from typing import Any
from uuid import UUID

from quantumco.identity.application.auth import Authentication
from quantumco.identity.application.ports import EmailAlreadyUsedError
from quantumco.identity.domain.email import EmailAddress
from quantumco.identity.domain.user import User
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.scenarios.domain.workspace import Workspace
from quantumco.syntax_analysis.application.queries import GetPolygonStats

from .support import FixedClock


class PlainHasher:
    """Só para testes: rápido e determinístico (produção usa Argon2id)."""

    def hash(self, password: str) -> str:
        return "plain$" + password

    def verify(self, password_hash: str, password: str) -> bool:
        return password_hash == "plain$" + password


class Users:
    def __init__(self) -> None:
        self.by_mail: dict[str, User] = {}

    def add(self, user: User) -> None:
        if str(user.email) in self.by_mail:
            raise EmailAlreadyUsedError(str(user.email))
        self.by_mail[str(user.email)] = user

    def by_email(self, email: EmailAddress) -> User | None:
        return self.by_mail.get(str(email))

    def by_id(self, user_id: UUID) -> User | None:
        return next((u for u in self.by_mail.values() if u.user_id == user_id), None)


class Sessions:
    def __init__(self) -> None:
        self.tokens: dict[str, UUID] = {}

    def create(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(16)
        self.tokens[token] = user_id
        return token

    def user_for(self, token: str) -> UUID | None:
        return self.tokens.get(token)

    def revoke(self, token: str) -> None:
        self.tokens.pop(token, None)


class WorkspaceStore:
    def __init__(self) -> None:
        self.items: dict[UUID, Workspace] = {}

    def list_for(self, owner_id: UUID) -> list[Workspace]:
        return [deepcopy(w) for w in self.items.values() if w.owner_id == owner_id]

    def get(self, workspace_id: UUID) -> Workspace | None:
        w = self.items.get(workspace_id)
        return deepcopy(w) if w else None

    def save(self, workspace: Workspace) -> None:
        self.items[workspace.workspace_id] = deepcopy(workspace)

    def delete(self, workspace_id: UUID) -> None:
        self.items.pop(workspace_id, None)


class PolygonStats:
    def stats(self, ring: list[tuple[float, float]]) -> Mapping[str, Any] | None:
        return {
            "territory": {"area_km2": 1.0, "perimeter_km": 4.0, "vertices": len(ring)},
            "network": {"links": 10, "km": 2.5, "by_radius": {}},
        }


def platform() -> tuple[Authentication, Workspaces, GetPolygonStats]:
    clock = FixedClock()
    auth = Authentication(users=Users(), hasher=PlainHasher(), sessions=Sessions(), clock=clock)
    return (
        auth,
        Workspaces(repository=WorkspaceStore(), clock=clock),
        GetPolygonStats(PolygonStats()),
    )
