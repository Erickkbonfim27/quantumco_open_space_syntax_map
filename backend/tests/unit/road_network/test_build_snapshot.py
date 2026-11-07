from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from shapely.geometry import Polygon

from quantumco.road_network.application.build_snapshot import BuildSnapshot, UnknownCityError
from quantumco.road_network.domain.city import City, CityStatus
from quantumco.road_network.domain.osm import OsmExtract, Zone
from quantumco.road_network.domain.snapshot import NetworkSnapshot, SnapshotIngested
from quantumco.road_network.domain.study_area import StudyArea
from quantumco.road_network.infrastructure.manifest import snapshot_name
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

from .conftest import way

NOW = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
OSM_BASE = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)


ITAPEMA = City("4208302", "Itapema", "SC", "itapema", 296608, 7000.0, 31982)


class Registry:
    def __init__(self, *cities: City) -> None:
        self.items = {c.ibge_code: c for c in cities}

    def get(self, ibge_code: str) -> City | None:
        return self.items.get(ibge_code)

    def all(self) -> list[City]:
        return list(self.items.values())

    def add(self, city: City) -> None:
        self.items[city.ibge_code] = city

    def set_status(self, ibge_code: str, status: CityStatus) -> None:
        self.items[ibge_code] = replace(self.items[ibge_code], status=status)


class FakeSource:
    def __init__(self) -> None:
        self.areas: list[StudyArea] = []

    def fetch(self, area: StudyArea) -> OsmExtract:
        self.areas.append(area)
        municipality = Polygon([(-100, -100), (100, -100), (100, 100), (-100, 100)])
        return OsmExtract(
            ways=(
                way(1, [(1, 0, 0), (2, 50, 0), (3, 90, 0)]),
                way(2, [(2, 50, 0), (4, 50, 50)]),
                way(3, [(3, 90, 0), (5, 300, 0)], highway="track"),  # meio no buffer
                way(4, [(6, -50, -50), (7, -40, -50)], highway="track"),  # track no município
                way(5, [(8, -90, 90), (9, -80, 90)]),  # ilha
                way(6, [(2, 50, 0), (10, 60, -20)], highway="service", service="driveway"),
            ),
            municipality=municipality,
            osm_base_timestamp=OSM_BASE,
            source="fake",
        )


class MemoryRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[NetworkSnapshot, str]] = []

    def save(self, snapshot: NetworkSnapshot, methodology_version: str) -> str:
        self.saved.append((snapshot, methodology_version))
        return "memory://snapshot"


class FixedClock:
    def now(self) -> datetime:
        return NOW


def test_build_snapshot_end_to_end(methodology: YamlMethodology) -> None:
    repository = MemoryRepository()
    source = FakeSource()
    result = BuildSnapshot(source, methodology, repository, FixedClock(), Registry(ITAPEMA))(
        "4208302"
    )
    # a área de estudo é a da cidade do cadastro (código + relação + faixa + CRS)
    assert source.areas == [StudyArea("4208302", 296608, 7000.0, 31982)]
    assert snapshot_name(result.snapshot) == "snapshot-4208302-20261108T020000Z"

    snapshot = result.snapshot
    report = snapshot.report
    assert report.ways_received == 6
    assert report.ways_accepted == 4
    assert report.rejected_by_reason == {
        "buffer_only_class_in_result_zone": 1,
        "private_service": 1,
    }
    assert {link.osm_way_id for link in snapshot.links} == {1, 2, 3}
    assert [link.osm_way_id for link in snapshot.excluded_links] == [5]
    assert next(link for link in snapshot.links if link.osm_way_id == 3).zone is Zone.BUFFER
    assert snapshot.osm_base_timestamp == OSM_BASE
    assert snapshot.filter_version == "highway_filter.v1/base"

    events = snapshot.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], SnapshotIngested)
    assert snapshot.pull_events() == []
    assert repository.saved[0][1] == methodology.version()


def test_build_snapshot_needs_a_registered_city(methodology: YamlMethodology) -> None:
    build = BuildSnapshot(FakeSource(), methodology, MemoryRepository(), FixedClock(), Registry())
    with pytest.raises(UnknownCityError, match="cidade adicionar 4208302"):
        build("4208302")
