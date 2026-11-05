from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from quantumco.territory.domain.profile import TractOverlap, ZoneOverlap
from quantumco.territory.domain.records import LayerData

Ring = Sequence[tuple[float, float]]


class LayerSource(Protocol):
    """Baixa e normaliza uma fonte aberta. Uma fonte pode render várias camadas (ex.: SGB)."""

    @property
    def name(self) -> str: ...

    def fetch(self) -> Sequence[LayerData]: ...


class TerritoryRepository(Protocol):
    def replace(self, data: LayerData, fetched_at: datetime) -> None:
        """Substitui a camada inteira numa transação (quem lê nunca vê camada pela metade)."""
        ...

    def layers(self) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class PlaceCount:
    layer: str
    kind: str
    count: int
    flagged: int = 0  # ex.: estabelecimentos de saúde que atendem pelo SUS


@dataclass(frozen=True, slots=True)
class NamedPlace:
    layer: str
    kind: str
    name: str


@dataclass(frozen=True, slots=True)
class PolygonOverlaps:
    area_m2: float
    tracts: Sequence[TractOverlap]
    zones: Sequence[ZoneOverlap]
    place_counts: Sequence[PlaceCount]
    named_places: Sequence[NamedPlace] = field(default_factory=tuple)
    # para desenhar (mapa e blocos do painel): pontos [lon, lat, "camada:tipo"] (amostra) e zonas
    # recortadas pelo polígono, em GeoJSON WGS84
    points: Sequence[tuple[float, float, str]] = field(default_factory=tuple)
    zone_shapes: Sequence[Mapping[str, Any]] = field(default_factory=tuple)


class TerritoryReader(Protocol):
    def overlaps(self, ring: Ring) -> PolygonOverlaps | None:
        """None quando nenhuma camada territorial foi importada ainda."""
        ...

    def layers(self) -> Sequence[Mapping[str, Any]]: ...
