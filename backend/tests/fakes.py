"""Implementações em memória das portas, para testar a API sem banco."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from quantumco.bootstrap.platform import Platform
from quantumco.identity.application.account import AccountEmails
from quantumco.identity.application.auth import Authentication
from quantumco.identity.application.ports import EmailAlreadyUsedError
from quantumco.identity.application.profile import Profile
from quantumco.identity.domain.email import EmailAddress, EmailMessage
from quantumco.identity.domain.tokens import EmailToken, TokenPurpose
from quantumco.identity.domain.user import User
from quantumco.identity.infrastructure.email_templates import BrandedAccountMessages
from quantumco.scenarios.application.ports import (
    EditRejectedError,
    QueueUnavailableError,
    RunCounts,
)
from quantumco.scenarios.application.runs import ScenarioRuns
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.scenarios.domain.network_edits import NetworkEdit
from quantumco.scenarios.domain.run import RunQuota, RunStatus, ScenarioRun
from quantumco.scenarios.domain.workspace import Workspace
from quantumco.syntax_analysis.application.queries import GetPolygonStats
from quantumco.territory.application.ports import NamedPlace, PlaceCount, PolygonOverlaps
from quantumco.territory.application.queries import GetPolygonProfile
from quantumco.territory.domain.profile import BuildingStats, GridStat, TractOverlap, ZoneOverlap

from .support import FixedClock

TINY_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


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

    def update(self, user: User, now: datetime) -> None:
        other = self.by_mail.get(str(user.email))
        if other is not None and other.user_id != user.user_id:
            raise EmailAlreadyUsedError(str(user.email))
        self.by_mail = {k: v for k, v in self.by_mail.items() if v.user_id != user.user_id}
        self.by_mail[str(user.email)] = user

    def set_avatar(
        self, user_id: UUID, key: str | None, media_type: str | None, now: datetime
    ) -> None:
        user = self.by_id(user_id)
        assert user is not None
        self.by_mail[str(user.email)] = replace(
            user, avatar_key=key, avatar_updated_at=now if key else None
        )


class Sessions:
    def __init__(self) -> None:
        self.tokens: dict[str, UUID] = {}

    def revoke_all(self, user_id: UUID) -> int:
        mine = [t for t, u in self.tokens.items() if u == user_id]
        for token in mine:
            del self.tokens[token]
        return len(mine)

    def create(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(16)
        self.tokens[token] = user_id
        return token

    def user_for(self, token: str) -> UUID | None:
        return self.tokens.get(token)

    def revoke(self, token: str) -> None:
        self.tokens.pop(token, None)


class Tokens:
    """Links de e-mail em memória (token em claro como chave: só para testes)."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def issue(
        self,
        user_id: UUID,
        purpose: TokenPurpose,
        *,
        now: datetime,
        ttl: timedelta,
        new_email: EmailAddress | None = None,
    ) -> str:
        for item in self.items.values():
            if item["user_id"] == user_id and item["purpose"] == purpose:
                item["used"] = True
        token = secrets.token_urlsafe(16)
        self.items[token] = {
            "user_id": user_id,
            "purpose": purpose,
            "new_email": new_email,
            "created_at": now,
            "expires_at": now + ttl,
            "used": False,
        }
        return token

    def consume(
        self, token: str, purposes: tuple[TokenPurpose, ...], now: datetime
    ) -> EmailToken | None:
        item = self.items.get(token)
        if not item or item["used"] or item["expires_at"] <= now or item["purpose"] not in purposes:
            return None
        item["used"] = True
        return EmailToken(item["user_id"], item["purpose"], item["new_email"], item["created_at"])

    def last_issued(self, user_id: UUID, purpose: TokenPurpose) -> datetime | None:
        times = [
            i["created_at"]
            for i in self.items.values()
            if i["user_id"] == user_id and i["purpose"] == purpose
        ]
        return max(times) if times else None


class Mailbox:
    """Mailer falso: guarda as mensagens (nenhum e-mail sai dos testes)."""

    def __init__(self, *, down: bool = False) -> None:
        self.sent: list[EmailMessage] = []
        self.down = down

    def send(self, message: EmailMessage) -> str:
        from quantumco.identity.application.ports import MailDeliveryError  # noqa: PLC0415

        if self.down:
            raise MailDeliveryError("provedor fora do ar")
        self.sent.append(message)
        return f"fake-{len(self.sent)}"

    def last_link(self, to: str | None = None) -> str:
        """Token do último link enviado (para `to`, se informado)."""
        for message in reversed(self.sent):
            if to is None or str(message.to[0]) == to:
                match = re.search(r"token=([A-Za-z0-9_-]+)", message.text)
                if match:
                    return match.group(1)
        raise AssertionError("nenhum link enviado")


class AvatarFiles:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, content: bytes, media_type: str) -> None:
        self.objects[key] = content

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)


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


class RunStore:
    """Pedidos de cálculo em memória (a ordem de inserção é a ordem da fila)."""

    def __init__(self) -> None:
        self.items: dict[UUID, ScenarioRun] = {}

    def add(self, run: ScenarioRun) -> None:
        self.items[run.run_id] = deepcopy(run)

    def save(self, run: ScenarioRun) -> bool:
        if run.run_id not in self.items:
            return False
        self.items[run.run_id] = deepcopy(run)
        return True

    def get(self, run_id: UUID) -> ScenarioRun | None:
        run = self.items.get(run_id)
        return deepcopy(run) if run else None

    def latest_for(self, workspace_id: UUID) -> ScenarioRun | None:
        found = [r for r in self.items.values() if r.workspace_id == workspace_id]
        return deepcopy(found[-1]) if found else None

    def counts(self, owner_id: UUID, since: datetime) -> RunCounts:
        runs = list(self.items.values())
        mine = [r for r in runs if r.owner_id == owner_id]
        return RunCounts(
            active_for_user=sum(r.active for r in mine),
            today_for_user=sum(
                r.created_at >= since and r.status != RunStatus.CANCELED for r in mine
            ),
            queued_total=sum(r.status == RunStatus.QUEUED for r in runs),
            running_total=sum(r.status == RunStatus.RUNNING for r in runs),
        )

    def position(self, run: ScenarioRun) -> int:
        queued = [r.run_id for r in self.items.values() if r.status == RunStatus.QUEUED]
        return queued.index(run.run_id) + 1

    def expected_engine_seconds(self) -> float | None:
        return 30.0

    def queued_ids(self) -> list[UUID]:
        return [r.run_id for r in self.items.values() if r.status == RunStatus.QUEUED]


class Queue:
    def __init__(self, *, down: bool = False) -> None:
        self.jobs: list[UUID] = []
        self.down = down

    def enqueue(self, run_id: UUID) -> None:
        if self.down:
            raise QueueUnavailableError("redis fora")
        self.jobs.append(run_id)

    def contains(self, run_id: UUID) -> bool:
        return run_id in self.jobs

    def workers(self) -> int | None:
        return 2


class Engine:
    """Motor falso: passa pelas etapas e devolve um resumo (ou recusa as edições)."""

    def __init__(self, reject: str | None = None) -> None:
        self.reject = reject
        self.calls: list[tuple[str, int]] = []
        self.forgotten: list[str] = []

    def run(
        self, name: str, edits: Sequence[NetworkEdit], on_stage: Callable[[str], None]
    ) -> Mapping[str, Any]:
        self.calls.append((name, len(edits)))
        for stage in ("loading", "editing", "engine", "comparing"):
            on_stage(stage)
        if self.reject:
            raise EditRejectedError(self.reject)
        on_stage("saving")
        return {"name": name, "engine_seconds": 12.5, "summary": {"nain_n": {"km_up": 1.0}}}

    def forget(self, name: str) -> None:
        self.forgotten.append(name)


class Identity:
    """As peças de identidade de um `platform()` de teste, para inspecionar nos testes."""

    def __init__(self, clock: Any) -> None:
        self.users, self.sessions, self.hasher = Users(), Sessions(), PlainHasher()
        self.tokens, self.mailbox, self.files = Tokens(), Mailbox(), AvatarFiles()
        self.clock = clock


def platform(
    *,
    queue: Queue | None = None,
    quota: RunQuota | None = None,
    identity: Identity | None = None,
    clock: Any = None,
) -> Platform:
    clock = clock or FixedClock()
    ident = identity or Identity(clock)
    users, sessions, hasher = ident.users, ident.sessions, ident.hasher
    workspaces = Workspaces(repository=WorkspaceStore(), clock=clock)
    runs = ScenarioRuns(
        workspaces=workspaces,
        runs=RunStore(),
        queue=queue if queue is not None else Queue(),
        clock=clock,
        quota=quota or RunQuota(),
    )
    forgotten: list[str] = []
    return Platform(
        auth=Authentication(users=users, hasher=hasher, sessions=sessions, clock=clock),
        profile=Profile(users=users, avatars=ident.files, clock=clock),
        workspaces=workspaces,
        runs=runs,
        polygon_stats=GetPolygonStats(PolygonStats()),
        forget_result=forgotten.append,
        account=AccountEmails(
            users=users,
            tokens=ident.tokens,
            sessions=sessions,
            hasher=hasher,
            mailer=ident.mailbox,
            messages=BrandedAccountMessages(),
            clock=clock,
        ),
    )


class TerritoryReader:
    """Um setor com metade dos domicílios dentro, um setor de risco e uma suscetibilidade."""

    def __init__(self, empty: bool = False) -> None:
        self._empty = empty
        self.tiles: list[tuple[int, int, int]] = []

    def layers(self) -> list[Mapping[str, Any]]:
        return [] if self._empty else [{"layer": "setores", "rows": 1, "source": "IBGE"}]

    def map_layer(self, name: str) -> bytes | None:
        return None if self._empty else b'{"type":"FeatureCollection","features":[]}'

    def images(self) -> list[Mapping[str, Any]]:
        if self._empty:
            return []
        legend = [{"label": "> 30%", "color": "#FF6B5E"}]
        return [{"layer": "declividade", "bounds": [-49.1, -27.3, -48.7, -26.9],
                 "legend": legend, "version": "2026-11-06T00:00:00+00:00"}]  # fmt: skip

    def image(self, layer: str) -> bytes | None:
        return TINY_PNG if not self._empty and layer == "declividade" else None

    def building_tile(self, z: int, x: int, y: int) -> bytes:
        self.tiles.append((z, x, y))
        return b"" if self._empty else b"\x1a\x02mvt"

    def overlaps(self, ring: Sequence[tuple[float, float]]) -> PolygonOverlaps | None:
        if self._empty:
            return None
        tract = TractOverlap(
            code="420290905000001",
            attrs={"people": 500, "households": 200, "dwellings": 220, "heads": 200,
                   "income_mean": 4000.0, "sc_base": 200, "sc_sidewalk": 150},
            area_share=0.9, addresses_in=100, addresses_all=200,
        )  # fmt: skip
        risk = ZoneOverlap("risco", "Alto", "Deslizamento", {"people": 40, "households": 10},
                           area_in_m2=5_000, area_total_m2=10_000)  # fmt: skip
        flood = ZoneOverlap("suscet_inundacao", "Alta", "Inundação", {}, 250_000, 900_000)
        return PolygonOverlaps(
            area_m2=1_000_000,
            tracts=[tract],
            zones=[risk, flood],
            place_counts=[
                PlaceCount("cnefe", "domicilio", 100),
                PlaceCount("cnes", "hospital", 1, 1),
                PlaceCount("lugares", "comercio", 12),
                PlaceCount("lugares", "alimentacao", 5),
            ],
            named_places=[NamedPlace("cnes", "hospital", "Hospital Azambuja")],
            imported=frozenset({"setores", "lugares", "edificacoes"}),
            grid=[
                GridStat(
                    "declividade",
                    "continuous",
                    1000,
                    mean=12.5,
                    minimum=0.0,
                    maximum=48.0,
                    p10=1.0,
                    p50=10.0,
                    p90=31.0,
                ),
                GridStat("mb_classe", "categorical", 1000, histogram={24.0: 700, 3.0: 300}),
            ],
            buildings=[
                BuildingStats("OpenStreetMap", 40, 30_000, 10, 65.0),
                BuildingStats("Microsoft ML Buildings", 160, 90_000, 0, 0.0),
            ],
        )


def territory(empty: bool = False) -> GetPolygonProfile:
    return GetPolygonProfile(TerritoryReader(empty))
