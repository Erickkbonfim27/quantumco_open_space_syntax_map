"""Registros das camadas territoriais, já normalizados (geometria em GeoJSON WGS84)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return len(self.tracts) + len(self.zones) + len(self.places) + len(self.addresses)
