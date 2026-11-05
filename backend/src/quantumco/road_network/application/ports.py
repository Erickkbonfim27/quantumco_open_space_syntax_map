from __future__ import annotations

from typing import Protocol

from quantumco.road_network.domain.highway_filter import HighwayFilter
from quantumco.road_network.domain.osm import OsmExtract
from quantumco.road_network.domain.snapshot import NetworkSnapshot
from quantumco.road_network.domain.study_area import StudyArea


class OsmWaySource(Protocol):
    """Entrega as vias do OSM da área de estudo (com buffer), projetadas no CRS da área."""

    def fetch(self, area: StudyArea) -> OsmExtract: ...


class MethodologyProvider(Protocol):
    def study_area(self) -> StudyArea: ...

    def highway_filter(self) -> HighwayFilter: ...

    def version(self) -> str: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: NetworkSnapshot, methodology_version: str) -> str:
        """Persiste o snapshot e devolve onde ele ficou."""
        ...
