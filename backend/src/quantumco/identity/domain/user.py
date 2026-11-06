from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any
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


THEMES = ("system", "light", "dark")
_BASEMAP = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def clean_preferences(raw: Mapping[str, Any]) -> dict[str, str]:
    """Só as preferências conhecidas: tema da interface e fundo do mapa."""
    prefs: dict[str, str] = {}
    theme = raw.get("theme")
    if theme is not None:
        if theme not in THEMES:
            raise InvalidUserError("Tema desconhecido.")
        prefs["theme"] = str(theme)
    basemap = raw.get("basemap")
    if basemap is not None:
        if not isinstance(basemap, str) or not _BASEMAP.match(basemap):
            raise InvalidUserError("Fundo de mapa desconhecido.")
        prefs["basemap"] = basemap
    return prefs


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    name: str
    email: EmailAddress
    organization: str | None
    password_hash: str
    created_at: datetime
    preferences: Mapping[str, str] = field(default_factory=dict)
    avatar_updated_at: datetime | None = None  # None = sem foto (a tela mostra as iniciais)
    avatar_key: str | None = None  # objeto no armazenamento de arquivos (RustFS)
    email_verified_at: datetime | None = None
    pending_email: EmailAddress | None = None  # troca pedida, esperando a confirmação

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

    def with_profile(
        self,
        *,
        name: str | None = None,
        organization: str | None = None,
        clear_organization: bool = False,
        preferences: Mapping[str, Any] | None = None,
    ) -> User:
        prefs = dict(self.preferences)
        if preferences is not None:
            prefs.update(clean_preferences(preferences))
        return replace(
            self,
            name=self.name if name is None else name,
            organization=None
            if clear_organization
            else (self.organization if organization is None else organization),
            preferences=prefs,
        )

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None

    def with_pending_email(self, email: EmailAddress | None) -> User:
        """Guarda o e-mail novo até a confirmação pelo link (None cancela a troca)."""
        return replace(self, pending_email=email)

    def confirm_email(self, now: datetime) -> User:
        return replace(self, email_verified_at=self.email_verified_at or now)

    def apply_pending_email(self, email: EmailAddress, now: datetime) -> User:
        """Troca confirmada: o e-mail novo passa a valer, já verificado."""
        return replace(self, email=email, pending_email=None, email_verified_at=now)

    def with_password_hash(self, password_hash: str) -> User:
        return replace(self, password_hash=password_hash)

    @property
    def initials(self) -> str:
        parts = self.name.split()
        return "".join(p[0] for p in parts[:2]).upper()
