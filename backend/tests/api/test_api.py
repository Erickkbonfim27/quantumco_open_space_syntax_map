from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.build_snapshot import BuildSnapshot
from quantumco.road_network.domain.osm import OsmExtract, OsmWay
from quantumco.road_network.domain.study_area import StudyArea
from quantumco.road_network.infrastructure.file_snapshot_repository import FileSnapshotRepository
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

METHODOLOGY_V1 = Path(__file__).resolve().parents[3] / "methodology" / "v1"

# coordenadas reais de Brusque em UTM 22S, para a reprojeção dar lon/lat plausíveis
X0, Y0 = 700_000.0, 7_000_000.0


def _way(osm_id: int, nodes: list[tuple[int, float, float]]) -> OsmWay:
    return OsmWay(
        osm_id=osm_id,
        node_ids=tuple(n for n, _, _ in nodes),
        coords=tuple((X0 + x, Y0 + y) for _, x, y in nodes),
        tags={"highway": "residential"},
    )


class FakeSource:
    def fetch(self, area: StudyArea) -> OsmExtract:
        return OsmExtract(
            ways=(
                _way(1, [(1, 0, 0), (2, 100, 0)]),
                _way(2, [(2, 100, 0), (3, 100, 100)]),
            ),
            municipality=Polygon(
                [
                    (X0 - 500, Y0 - 500),
                    (X0 + 500, Y0 - 500),
                    (X0 + 500, Y0 + 500),
                    (X0 - 500, Y0 + 500),
                ]
            ),
            osm_base_timestamp=datetime(2026, 11, 8, 2, 0, tzinfo=UTC),
            source="fake",
        )


class FixedClock:
    def now(self) -> datetime:
        return datetime(2026, 11, 8, 3, 0, tzinfo=UTC)


def settings_for(data_dir: Path) -> Settings:
    return Settings.from_env(
        {"QC_DATA_DIR": str(data_dir), "QC_METHODOLOGY_DIR": str(METHODOLOGY_V1)}
    )


@pytest.fixture
def client_with_snapshot(tmp_path: Path) -> TestClient:
    BuildSnapshot(
        FakeSource(),
        YamlMethodology(METHODOLOGY_V1),
        FileSnapshotRepository(tmp_path / "snapshots"),
        FixedClock(),
    )()
    return TestClient(create_app(settings_for(tmp_path)))


def test_health_without_snapshot(tmp_path: Path) -> None:
    client = TestClient(create_app(settings_for(tmp_path)))
    assert client.get("/health").json() == {"status": "ok", "snapshot": None}
    response = client.get("/api/v1/network/links")
    assert response.status_code == 503
    assert "snapshot build" in response.json()["detail"]


def test_manifest_and_health(client_with_snapshot: TestClient) -> None:
    manifest = client_with_snapshot.get("/api/v1/network/manifest").json()
    assert manifest["study_area"]["ibge_code"] == "4202909"
    assert manifest["cleaning_report"]["links_kept"] == 2
    health = client_with_snapshot.get("/health").json()
    assert health["snapshot"] == manifest["snapshot_id"]


def test_links_are_geojson_in_wgs84(client_with_snapshot: TestClient) -> None:
    response = client_with_snapshot.get("/api/v1/network/links")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/geo+json")
    collection = json.loads(response.content)
    assert len(collection["features"]) == 2
    lon, lat = collection["features"][0]["geometry"]["coordinates"][0]
    assert -54 < lon < -48
    assert -30 < lat < -25
    assert set(collection["features"][0]["properties"]) >= {"link_id", "highway", "zone"}


def test_etag_returns_304(client_with_snapshot: TestClient) -> None:
    first = client_with_snapshot.get("/api/v1/network/municipality")
    etag = first.headers["etag"]
    second = client_with_snapshot.get(
        "/api/v1/network/municipality", headers={"If-None-Match": etag}
    )
    assert second.status_code == 304


def test_gzip(client_with_snapshot: TestClient) -> None:
    response = client_with_snapshot.get(
        "/api/v1/network/links", headers={"Accept-Encoding": "gzip"}
    )
    assert response.status_code == 200
