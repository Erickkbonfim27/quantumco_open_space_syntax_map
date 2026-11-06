from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from quantumco.territory.domain.profile import BuildingStats, GridStat, TractOverlap, ZoneOverlap
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
    # fase B: camadas da grade de 30 m e edificações (None = camada não importada)
    grid: Sequence[GridStat] = field(default_factory=tuple)
    buildings: Sequence[BuildingStats] | None = None
    # amostra para desenhar: [lon, lat, área m², do OSM?] pelo ponto interno da pegada
    building_points: Sequence[tuple[float, float, float, bool]] = field(default_factory=tuple)


class TerritoryReader(Protocol):
    def overlaps(self, ring: Ring) -> PolygonOverlaps | None:
        """None quando nenhuma camada territorial foi importada ainda."""
        ...

    def layers(self) -> Sequence[Mapping[str, Any]]: ...

    def map_layer(self, name: str) -> bytes | None:
        """FeatureCollection (GeoJSON WGS84) de uma camada para o mapa da cidade inteira."""
        ...

    def images(self) -> Sequence[Mapping[str, Any]]:
        """Imagens prontas para o mapa: camada, limites (WGS84) e legenda."""
        ...

    def image(self, layer: str) -> bytes | None:
        """PNG de uma camada da grade; None se não houver."""
        ...

    def building_tile(self, z: int, x: int, y: int) -> bytes:
        """Tile vetorial (MVT) das edificações; vazio quando não há prédio no tile."""
        ...
