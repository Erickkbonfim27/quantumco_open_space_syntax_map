from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quantumco.road_network.domain.city import City, CityStatus
from quantumco.road_network.domain.highway_filter import HighwayFilter
from quantumco.road_network.domain.osm import OsmExtract
from quantumco.road_network.domain.snapshot import NetworkSnapshot
from quantumco.road_network.domain.study_area import StudyArea


class OsmWaySource(Protocol):
    """Entrega as vias do OSM da área de estudo (com buffer), projetadas no CRS da área."""

    def fetch(self, area: StudyArea) -> OsmExtract: ...


class MethodologyProvider(Protocol):
    def buffer_m(self) -> float:
        """Faixa externa da área de estudo (regra da metodologia, igual para toda cidade)."""
        ...

    def highway_filter(self) -> HighwayFilter: ...

    def version(self) -> str: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: NetworkSnapshot, methodology_version: str) -> str:
        """Persiste o snapshot, publica como o atual DA CIDADE e devolve onde ele ficou."""
        ...


class CityRegistry(Protocol):
    """Cadastro das cidades (road_network.study_areas)."""

    def get(self, ibge_code: str) -> City | None: ...

    def all(self) -> list[City]: ...

    def add(self, city: City) -> None: ...

    def set_status(self, ibge_code: str, status: CityStatus) -> None: ...


@dataclass(frozen=True, slots=True)
class Municipality:
    """Município no diretório do IBGE (API de localidades)."""

    ibge_code: str
    name: str
    uf: str


class MunicipalityDirectory(Protocol):
    def lookup(self, ibge_code: str) -> Municipality | None: ...


@dataclass(frozen=True, slots=True)
class BoundaryRef:
    """Relação de limite municipal no OSM, achada pelo `IBGE:GEOCODIGO`."""

    osm_relation_id: int
    center: tuple[float, float]  # lon, lat


class BoundaryLocator(Protocol):
    def find(self, ibge_code: str) -> BoundaryRef | None: ...
