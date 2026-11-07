"""Integração com PostGIS.

Rodar com: QC_TEST_DATABASE_URL=postgresql://…/quantumco_test uv run pytest -m db

Os testes recriam os schemas: por segurança, só rodam num banco cujo nome contém "test".
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import numpy as np
import pytest
from shapely.geometry import Polygon

from quantumco.platform.postgres import connect, migrate, pool
from quantumco.road_network.application.build_snapshot import BuildSnapshot
from quantumco.road_network.domain.city import City
from quantumco.road_network.domain.osm import OsmExtract, OsmWay
from quantumco.road_network.domain.study_area import StudyArea
from quantumco.road_network.infrastructure.postgis_cities import PostgisCityRegistry
from quantumco.road_network.infrastructure.postgis_network_reader import PostgisNetworkReader
from quantumco.road_network.infrastructure.postgis_snapshot_repository import (
    PostgisSnapshotRepository,
)
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology
from quantumco.syntax_analysis.application.ports import AnalysisResult
from quantumco.syntax_analysis.infrastructure.postgis_analysis_repository import (
    PostgisAnalysisRepository,
)
from quantumco.syntax_analysis.infrastructure.postgis_network_source import PostgisNetworkSource
from quantumco.syntax_analysis.infrastructure.postgis_syntax_map_reader import (
    PostgisSyntaxMapReader,
)

from ..support import METHODOLOGY_V1, X0, Y0, FixedClock

URL = os.environ.get("QC_TEST_DATABASE_URL", "")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not URL, reason="QC_TEST_DATABASE_URL não definido"),
]


class Source:
    def __init__(self, osm_minute: int) -> None:
        self._minute = osm_minute

    def fetch(self, area: StudyArea) -> OsmExtract:
        def way(osm_id: int, nodes: list[tuple[int, float, float]]) -> OsmWay:
            return OsmWay(
                osm_id=osm_id,
                node_ids=tuple(n for n, _, _ in nodes),
                coords=tuple((X0 + x, Y0 + y) for _, x, y in nodes),
                tags={"highway": "residential"},
            )

        return OsmExtract(
            ways=(
                way(1, [(1, 0, 0), (2, 100, 0)]),
                way(2, [(2, 100, 0), (3, 100, 100)]),
                way(3, [(8, 300, 300), (9, 320, 300)]),  # ilha → excluded
            ),
            municipality=Polygon(
                [
                    (X0 - 500, Y0 - 500),
                    (X0 + 500, Y0 - 500),
                    (X0 + 500, Y0 + 500),
                    (X0 - 500, Y0 + 500),
                ]
            ),
            osm_base_timestamp=datetime(2026, 11, 8, 2, self._minute, tzinfo=UTC),
            source="fake",
        )


@pytest.fixture(scope="module")
def database() -> str:
    with connect(URL) as conn:
        name = conn.execute("select current_database()").fetchone()
        assert name is not None
        if "test" not in str(name[0]):
            pytest.skip(f"banco {name[0]!r} não parece de teste; recuso recriar schemas")
        # todos os schemas da aplicação: as migrações recriam tudo do zero
        for schema in ("territory", "scenarios", "identity", "syntax_analysis", "road_network"):
            conn.execute(f"drop schema if exists {schema} cascade")
        conn.execute("drop table if exists public.schema_migrations")
        conn.commit()
    assert migrate(URL)[0] == "001_init"
    assert migrate(URL) == []  # idempotente
    return URL


BRUSQUE, ITAPEMA = "4202909", "4208302"


def build(url: str, minute: int, city: str = BRUSQUE) -> None:
    BuildSnapshot(
        Source(minute),
        YamlMethodology(METHODOLOGY_V1),
        PostgisSnapshotRepository(url),
        FixedClock(),
        PostgisCityRegistry(url),
    )(city)


def test_snapshot_roundtrip_and_atomic_publish(database: str) -> None:
    build(database, 0)
    build(database, 5)  # o segundo vira o atual
    with connect(database) as conn:
        current = conn.execute(
            "select count(*) filter (where is_current), count(*) from road_network.snapshots"
        ).fetchone()
        assert current == (1, 2)
        excluded = conn.execute(
            "select count(*) from road_network.links l join road_network.snapshots s "
            "using (snapshot_id) where s.is_current and l.excluded"
        ).fetchone()
        assert excluded == (1,)

    network = PostgisNetworkReader(pool(database)).current(BRUSQUE)
    assert network is not None
    links = json.loads(network.links_geojson)
    assert len(links["features"]) == 2  # a ilha fica fora do publicado
    lon, lat = links["features"][0]["geometry"]["coordinates"][0]
    assert -54 < lon < -48
    assert -30 < lat < -25
    municipality = json.loads(network.municipality_geojson)
    assert municipality["features"][0]["properties"]["ibge_code"] == "4202909"

    source = PostgisNetworkSource(database).latest(BRUSQUE)
    assert source is not None
    assert len(source.links) == 2
    assert source.snapshot_name == "snapshot-4202909-20261108T020500Z"
    assert source.crs_epsg == 31982


def test_publishing_another_city_keeps_brusque_current(database: str) -> None:
    registry = PostgisCityRegistry(database)
    assert registry.get(BRUSQUE) is not None  # semeada pela migração 012
    registry.add(City(ITAPEMA, "Itapema", "SC", "itapema", 296608, 7000.0, 31982))
    with connect(database) as conn:
        before = conn.execute(
            "select snapshot_id from road_network.snapshots where is_current and ibge_code = %s",
            (BRUSQUE,),
        ).fetchone()
    build(database, 5, ITAPEMA)  # mesmo carimbo do OSM do último de Brusque: nome não colide
    with connect(database) as conn:
        rows = dict(
            conn.execute(
                "select ibge_code, snapshot_id from road_network.snapshots where is_current"
            ).fetchall()
        )
    assert set(rows) == {BRUSQUE, ITAPEMA}
    assert before is not None
    assert rows[BRUSQUE] == before[0]
    assert PostgisNetworkReader(pool(database)).current(ITAPEMA) is not None


def test_analysis_roundtrip(database: str) -> None:
    source = PostgisNetworkSource(database).latest(BRUSQUE)
    assert source is not None
    ids = tuple(link.link_id for link in source.links)
    result = AnalysisResult(
        snapshot_id=source.snapshot_id,
        snapshot_name=source.snapshot_name,
        link_ids=ids,
        columns={"nain_n": np.array([0.2, np.nan]), "c_nain_n": np.array([6.0, np.nan])},
        manifest={"created_at": "2026-11-08T03:10:00+00:00", "preliminary": True},
        ibge_code=BRUSQUE,
    )
    PostgisAnalysisRepository(database).save(result)
    assert PostgisSyntaxMapReader(pool(database)).current(ITAPEMA) is None  # cada uma a sua
    syntax = PostgisSyntaxMapReader(pool(database)).current(BRUSQUE)
    assert syntax is not None
    features = {
        f["properties"]["link_id"]: f["properties"]
        for f in json.loads(syntax.links_geojson)["features"]
    }
    assert features[ids[0]]["nain_n"] == pytest.approx(0.2)
    assert features[ids[0]]["c_nain_n"] == 6
    assert features[ids[1]]["c_nain_n"] is None
