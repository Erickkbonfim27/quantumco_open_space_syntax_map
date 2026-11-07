from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Protocol

from quantumco.listings.domain.listing import SaleListing, SearchArea


class FeatureDisabledError(RuntimeError):
    pass


class RunAlreadyActiveError(RuntimeError):
    pass


class SourceBlockedError(RuntimeError):
    """A fonte recusou o acesso (ex.: 403 do Cloudflare). Não se tenta contornar."""

    def __init__(self, message: str, attempts: int = 1) -> None:
        super().__init__(message)
        self.attempts = attempts


class FeatureFlags(Protocol):
    def is_enabled(self, name: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class ListingPage:
    listings: Sequence[SaleListing]
    total: int  # quantos a fonte diz ter para a busca inteira
    attempts: int  # pedidos feitos para obter esta página (1 = sem nova tentativa)
    last: bool  # a fonte não tem mais nada para esta busca (a carga percorreu tudo)


class ListingSource(Protocol):
    @property
    def name(self) -> str: ...

    def pages(self, area: SearchArea, max_pages: int) -> Iterator[ListingPage]: ...


@dataclass(frozen=True, slots=True)
class MergeResult:
    new: int = 0
    changed: int = 0
    unchanged: int = 0


@dataclass(frozen=True, slots=True)
class Rejection:
    listing: SaleListing
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunTally:
    pages: int = 0
    received: int = 0
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    rejected: int = 0
    removed: int = 0
    located: int = 0
    attempts: int = 0
    total: int | None = None
    complete: bool = False


class ListingRepository(Protocol):
    def start_run(self, area: SearchArea, source: str) -> int:
        """Abre a carga; `RunAlreadyActiveError` se já há uma rodando para a fonte e a cidade."""
        ...

    def merge(self, run_id: int, area: SearchArea, listings: Sequence[SaleListing]) -> MergeResult:
        """Upsert idempotente de uma página (staging → histórico → estado atual)."""
        ...

    def reject(self, run_id: int, rejections: Sequence[Rejection]) -> None:
        """Quarentena. A linha boa que já existe fica como está; só conta como vista."""
        ...

    def progress(self, run_id: int, tally: RunTally) -> None:
        """Grava os contadores a cada página: o banco anda junto com o log."""
        ...

    def mark_removed(self, run_id: int, area: SearchArea, source: str) -> int:
        """Só depois de carga COMPLETA: quem não foi visto nesta carga ganha `removed_at`."""
        ...

    def finish_run(self, run_id: int, status: str, tally: RunTally, detail: str) -> None: ...
