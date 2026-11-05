from __future__ import annotations

from datetime import UTC, datetime

from shapely.geometry import Polygon

from quantumco.road_network.application.build_snapshot import BuildSnapshot
from quantumco.road_network.domain.osm import OsmExtract, Zone
from quantumco.road_network.domain.snapshot import NetworkSnapshot, SnapshotIngested
from quantumco.road_network.domain.study_area import StudyArea
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

from .conftest import way

NOW = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
OSM_BASE = datetime(2026, 11, 8, 2, 0, tzinfo=UTC)


class FakeSource:
    def fetch(self, area: StudyArea) -> OsmExtract:
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
    result = BuildSnapshot(FakeSource(), methodology, repository, FixedClock())()

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
