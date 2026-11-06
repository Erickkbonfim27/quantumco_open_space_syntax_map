"""Registros das camadas territoriais, já normalizados (geometria em GeoJSON WGS84)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

GeoJSON = Mapping[str, Any]
Number = float | None


@dataclass(frozen=True, slots=True)
class Tract:
    """Setor censitário do IBGE 2022 com os atributos que usamos (ver TRACT_ATTRS)."""

    code: str
    geometry: GeoJSON
    attrs: Mapping[str, Number]


@dataclass(frozen=True, slots=True)
class Zone:
    """Área de uma camada temática (setor de risco, classe de suscetibilidade)."""

    layer: str
    category: str
    process: str
    geometry: GeoJSON
    attrs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Place:
    """Ponto (endereço do CNEFE, estabelecimento de saúde…)."""

    layer: str
    kind: str
    lon: float
    lat: float
    name: str | None = None
    tract_code: str | None = None
    attrs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Address:
    """Ponto do índice de endereços: um número de um logradouro, ou o logradouro (number=None)."""

    street: str
    number: int | None
    locality: str | None
    cep: str | None
    lon: float
    lat: float
    units: int
    search_key: str


@dataclass(frozen=True, slots=True)
class Building:
    """Edificação (Overture buildings): pegada no chão e, quando houver, altura e andares."""

    building_id: str
    source: str  # conjunto de origem: OpenStreetMap, Microsoft ML Buildings, Google Open Buildings…
    geometry: GeoJSON
    height_m: float | None = None
    floors: int | None = None
    klass: str | None = None
    confidence: float | None = None  # do modelo de detecção (Google), 0..1


class GridKind(StrEnum):
    CONTINUOUS = "continuous"  # declividade, NDVI, calor: média e percentis no polígono
    CATEGORICAL = "categorical"  # classe do MapBiomas: fração da área por classe


@dataclass(frozen=True, slots=True)
class LegendItem:
    label: str
    color: str  # "#RRGGBB"


@dataclass(frozen=True, slots=True)
class RasterImage:
    """PNG pronto para o mapa (fonte `image` do MapLibre), com limites em WGS84."""

    png: bytes
    bounds: tuple[float, float, float, float]  # oeste, sul, leste, norte
    legend: Sequence[LegendItem] = ()

    def __post_init__(self) -> None:
        west, south, east, north = self.bounds
        if not (west < east and south < north):
            raise ValueError("limites da imagem invertidos")
        if not self.png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("a imagem precisa ser PNG")


@dataclass(frozen=True, slots=True)
class GridLayer:
    """Uma camada raster resumida na grade fixa de 30 m (territory/domain/grid.py)."""

    kind: GridKind
    values: Mapping[int, float]  # id da célula → valor (células sem dado ficam de fora)
    unit: str = ""
    image: RasterImage | None = None


@dataclass(frozen=True, slots=True)
class LayerData:
    """Uma camada inteira, pronta para substituir a anterior de mesmo nome."""

    layer: str
    source: str
    source_url: str
    license: str
    tracts: Sequence[Tract] = ()
    zones: Sequence[Zone] = ()
    places: Sequence[Place] = ()
    addresses: Sequence[Address] = ()
    buildings: Sequence[Building] = ()
    grid: GridLayer | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        grid = len(self.grid.values) if self.grid else 0
        return (
            len(self.tracts)
            + len(self.zones)
            + len(self.places)
            + len(self.addresses)
            + len(self.buildings)
            + grid
        )
