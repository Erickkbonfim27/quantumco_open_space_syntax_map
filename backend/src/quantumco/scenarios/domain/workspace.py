"""Cenário do usuário (design "Quantumco Plataforma"): um espaço de trabalho com polígonos.

Guarda nome, medida inicial, status, os polígonos desenhados e as edições da rede ("e se…":
remover, interditar, criar ou redesenhar vias), que um cálculo na fila transforma em resultado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from shapely.geometry import Polygon as ShapelyPolygon

from quantumco.scenarios.domain.common import BOUNDS, InvalidWorkspaceError
from quantumco.scenarios.domain.network_edits import NetworkEdit, check_edits

__all__ = ["BOUNDS", "InvalidWorkspaceError"]

MAX_VERTICES = 500
MAX_POLYGONS = 50


class Measure(StrEnum):
    NAIN = "nain"
    NACH = "nach"


class Status(StrEnum):
    RASCUNHO = "rascunho"
    EM_ANALISE = "em_analise"
    PUBLICADO = "publicado"


Ring = tuple[tuple[float, float], ...]  # (lon, lat), fechado


def _clean_name(name: str, fallback: str, limit: int = 120) -> str:
    clean = " ".join(name.split())[:limit]
    return clean or fallback


@dataclass(frozen=True, slots=True)
class AreaPolygon:
    polygon_id: UUID
    code: str
    name: str
    ring: Ring
    created_at: datetime

    def __post_init__(self) -> None:
        ring = list(self.ring)
        if len(ring) >= 2 and ring[0] != ring[-1]:
            ring.append(ring[0])
        if len(ring) < 4:
            raise InvalidWorkspaceError("O polígono precisa de pelo menos 3 vértices.")
        if len(ring) > MAX_VERTICES:
            raise InvalidWorkspaceError(f"No máximo {MAX_VERTICES} vértices.")
        west, south, east, north = BOUNDS
        if not all(west <= x <= east and south <= y <= north for x, y in ring):
            raise InvalidWorkspaceError("O polígono precisa estar em Brusque ou no entorno.")
        shape = ShapelyPolygon(ring)
        if not shape.is_valid or shape.area == 0:
            raise InvalidWorkspaceError("Polígono inválido (lados se cruzam).")
        object.__setattr__(self, "ring", tuple((float(x), float(y)) for x, y in ring))
        object.__setattr__(self, "name", _clean_name(self.name, self.code, 80))


@dataclass(slots=True)
class Workspace:
    """Agregado: o cenário e seus polígonos, sempre de um único dono."""

    workspace_id: UUID
    owner_id: UUID
    name: str
    measure: Measure
    status: Status
    created_at: datetime
    updated_at: datetime
    polygons: list[AreaPolygon] = field(default_factory=list)
    edits: list[NetworkEdit] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = _clean_name(self.name, "Cenário sem nome")

    @classmethod
    def create(cls, *, owner_id: UUID, name: str, measure: Measure, now: datetime) -> Workspace:
        return cls(uuid4(), owner_id, name, measure, Status.RASCUNHO, now, now)

    def next_code(self) -> str:
        used = {int(p.code.removeprefix("P-")) for p in self.polygons if p.code.startswith("P-")}
        n = 1
        while n in used:
            n += 1
        return f"P-{n:02d}"

    def add_polygon(self, *, name: str | None, ring: Ring, now: datetime) -> AreaPolygon:
        if len(self.polygons) >= MAX_POLYGONS:
            raise InvalidWorkspaceError(f"No máximo {MAX_POLYGONS} polígonos por cenário.")
        code = self.next_code()
        polygon = AreaPolygon(uuid4(), code, name or f"Polígono {code[2:]}", ring, now)
        self.polygons.append(polygon)
        self.updated_at = now
        return polygon

    def remove_polygon(self, polygon_id: UUID, now: datetime) -> None:
        before = len(self.polygons)
        self.polygons = [p for p in self.polygons if p.polygon_id != polygon_id]
        if len(self.polygons) == before:
            raise InvalidWorkspaceError("Polígono não encontrado.")
        self.updated_at = now

    def set_edits(self, edits: Sequence[NetworkEdit], now: datetime) -> None:
        """Substitui a lista de edições da rede (a tela manda a lista inteira)."""
        check_edits(edits)
        self.edits = list(edits)
        self.updated_at = now

    def update(
        self, *, name: str | None, measure: Measure | None, status: Status | None, now: datetime
    ) -> None:
        if name is not None:
            self.name = _clean_name(name, self.name)
        if measure is not None:
            self.measure = measure
        if status is not None:
            self.status = status
        self.updated_at = now
