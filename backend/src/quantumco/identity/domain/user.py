from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from quantumco.identity.domain.email import EmailAddress

MIN_PASSWORD = 8
MAX_PASSWORD = 128


class InvalidUserError(ValueError):
    pass


def check_password_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise InvalidUserError(f"A senha precisa ter pelo menos {MIN_PASSWORD} caracteres.")
    if len(password) > MAX_PASSWORD:
        raise InvalidUserError(f"A senha pode ter no máximo {MAX_PASSWORD} caracteres.")


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    name: str
    email: EmailAddress
    organization: str | None
    password_hash: str
    created_at: datetime

    def __post_init__(self) -> None:
        name = " ".join(self.name.split())
        if not name:
            raise InvalidUserError("Informe seu nome.")
        if len(name) > 120:
            raise InvalidUserError("Nome muito longo.")
        object.__setattr__(self, "name", name)
        org = " ".join((self.organization or "").split())[:160] or None
        object.__setattr__(self, "organization", org)

    @classmethod
    def register(
        cls,
        *,
        name: str,
        email: EmailAddress,
        organization: str | None,
        password_hash: str,
        now: datetime,
    ) -> User:
        return cls(uuid4(), name, email, organization, password_hash, now)

    @property
    def initials(self) -> str:
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper()
