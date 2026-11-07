"""Integração com PostGIS das camadas territoriais da fase B (grade de 30 m, prédios, imagens).

Rodar com: QC_TEST_DATABASE_URL=postgresql://…/quantumco_test uv run pytest -m db

Banco temporário local (dados só em memória; some ao parar o contêiner):

    docker run --rm -d --platform linux/amd64 --name qc-test-postgis \
        --tmpfs /var/lib/postgresql/data -p 127.0.0.1:55432:5432 \
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=quantumco_test postgis/postgis:17-3.5-alpine
    QC_TEST_DATABASE_URL=postgresql://postgres:test@127.0.0.1:55432/quantumco_test \
        uv run pytest -m db
    docker stop qc-test-postgis

Recria TODOS os schemas da aplicação: por segurança, só roda num banco cujo nome contém "test".
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from psycopg_pool import ConnectionPool
from pyproj import Transformer

from quantumco.platform.postgres import connect, migrate, pool
from quantumco.territory.domain.grid import BRUSQUE_GRID
from quantumco.territory.domain.records import (
    Building,
    GridKind,
    GridLayer,
    LayerData,
    LegendItem,
    RasterImage,
    Tract,
)
from quantumco.territory.infrastructure.postgis_territory import (
    PostgisTerritoryReader,
    PostgisTerritoryRepository,
)

from ..fakes import TINY_PNG

URL = os.environ.get("QC_TEST_DATABASE_URL", "")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not URL, reason="QC_TEST_DATABASE_URL não definido"),
]
SCHEMAS = ("territory", "scenarios", "identity", "syntax_analysis", "road_network")
WHEN = datetime(2026, 11, 6, 3, 0, tzinfo=UTC)
BRUSQUE, ITAPEMA = "4202909", "4208302"
TO_WGS84 = Transformer.from_crs(31982, 4326, always_xy=True)


def ring(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return [list(TO_WGS84.transform(x, y)) for x, y in corners]


def polygon(x0: float, y0: float, x1: float, y1: float) -> dict[str, object]:
    return {"type": "Polygon", "coordinates": [ring(x0, y0, x1, y1)]}


# setor quadrado de 600 m alinhado à grade, perto do centro de Brusque
SX, SY = 700_020.0, 7_000_020.0  # múltiplos de 30 → 20 × 20 células inteiras dentro
TRACT = (SX, SY, SX + 600, SY + 600)


@pytest.fixture(scope="module")
def db() -> Iterator[ConnectionPool]:
    with connect(URL) as conn:
        name = conn.execute("select current_database()").fetchone()
        assert name is not None
        if "test" not in str(name[0]):
            pytest.skip(f"banco {name[0]!r} não parece de teste; recuso recriar schemas")
        for schema in SCHEMAS:
            conn.execute(f"drop schema if exists {schema} cascade")
        conn.execute("drop table if exists public.schema_migrations")
        conn.commit()
    assert "009_territory_grid_buildings" in migrate(URL)
    p = pool(URL)
    repo = PostgisTerritoryRepository(p)
    repo.replace(
        BRUSQUE,
        LayerData(
            "setores", "IBGE", "u", "Fonte: IBGE",
            tracts=[Tract("420290905000001", polygon(*TRACT), {"people": 100})],
        ),
        WHEN,
    )  # fmt: skip
    yield p
    p.close()


def inside_cells() -> list[int]:
    x0, y0, x1, y1 = TRACT
    cells = []
    for row in range(BRUSQUE_GRID.nrows):
        y = BRUSQUE_GRID.north - (row + 0.5) * BRUSQUE_GRID.size
        if not y0 < y < y1:
            continue
        for col in range(BRUSQUE_GRID.ncols):
            x = BRUSQUE_GRID.west + (col + 0.5) * BRUSQUE_GRID.size
            if x0 < x < x1:
                cells.append(BRUSQUE_GRID.cell(col, row))
    return cells


def test_grid_is_cut_by_the_municipality_and_values_outside_are_dropped(
    db: ConnectionPool,
) -> None:
    cells = inside_cells()
    assert len(cells) == 400
    far = BRUSQUE_GRID.cell(0, 0)  # canto noroeste da grade, longe do setor
    values = {c: float(i % 10) for i, c in enumerate(cells)} | {far: 99.0}
    image = RasterImage(TINY_PNG, (-49.1, -27.3, -48.7, -26.9), [LegendItem("alto", "#FF6B5E")])
    PostgisTerritoryRepository(db).replace(
        BRUSQUE,
        LayerData("declividade", "SIGSC", "u", "derivado",
                  grid=GridLayer(GridKind.CONTINUOUS, values, unit="%", image=image)),
        WHEN,
    )  # fmt: skip
    with db.connection() as conn:
        (n,) = conn.execute("select count(*) from territory.grid").fetchone()  # type: ignore[misc]
        (too_far,) = conn.execute(  # type: ignore[misc]
            "select count(*) from territory.grid g, territory.tracts t "
            "where ST_Distance(g.geom, t.geom) > 1000 + 30"
        ).fetchone()
        (kept,) = conn.execute(  # type: ignore[misc]
            "select count(*) from territory.grid_values where layer = 'declividade'"
        ).fetchone()
        (meta,) = conn.execute(  # type: ignore[misc]
            "select meta from territory.layers where layer = 'declividade'"
        ).fetchone()
    # (600 + 2 × 1000)² com cantos arredondados: entre o quadrado interno e o externo
    assert 600**2 / 900 < n < 2600**2 / 900
    assert too_far == 0
    assert kept == 400  # a célula longe do município foi descartada
    assert meta == {"grid_kind": "continuous", "grid_unit": "%", "grid_cells": 400}

    reader = PostgisTerritoryReader(db)
    found = reader.overlaps(BRUSQUE, ring(*TRACT))
    assert found is not None
    [stat] = found.grid
    assert stat.layer == "declividade"
    assert stat.cells == 400
    assert stat.mean == pytest.approx(4.5)
    assert (stat.minimum, stat.maximum) == (0.0, 9.0)
    [img] = reader.images(BRUSQUE)
    assert img["layer"] == "declividade"
    assert img["legend"] == [{"label": "alto", "color": "#FF6B5E"}]
    assert reader.image(BRUSQUE, "declividade") == TINY_PNG


def test_categorical_grid_layer_is_a_histogram(db: ConnectionPool) -> None:
    cells = inside_cells()
    values = {c: (24.0 if i < 300 else 3.0) for i, c in enumerate(cells)}
    PostgisTerritoryRepository(db).replace(
        BRUSQUE,
        LayerData("mb_classe", "MapBiomas", "u", "CC BY 4.0",
                  grid=GridLayer(GridKind.CATEGORICAL, values)),
        WHEN,
    )  # fmt: skip
    found = PostgisTerritoryReader(db).overlaps(BRUSQUE, ring(*TRACT))
    assert found is not None
    by_layer = {s.layer: s for s in found.grid}
    assert by_layer["mb_classe"].histogram == {24.0: 300, 3.0: 100}
    assert by_layer["mb_classe"].mean is None


def test_buildings_count_by_point_on_surface_and_clip_footprint(db: ConnectionPool) -> None:
    reader = PostgisTerritoryReader(db)
    before = reader.overlaps(BRUSQUE, ring(*TRACT))
    assert before is not None
    assert before.buildings is None  # camada ainda não importada
    inside = polygon(SX + 100, SY + 100, SX + 110, SY + 110)  # 100 m², inteiro dentro
    # 20 m × 10 m cruzando a borda leste: 1/4 dentro, ponto interno fora
    edge = polygon(SX + 595, SY + 300, SX + 615, SY + 310)
    PostgisTerritoryRepository(db).replace(
        BRUSQUE,
        LayerData(
            "edificacoes", "Overture", "u", "ODbL",
            buildings=[
                Building("a", "OpenStreetMap", inside, height_m=9.0, floors=3),
                Building("b", "Microsoft ML Buildings", edge),
            ],
        ),
        WHEN,
    )  # fmt: skip
    found = reader.overlaps(BRUSQUE, ring(*TRACT))
    assert found is not None
    assert found.buildings is not None
    stats = {s.source: s for s in found.buildings}
    assert stats["OpenStreetMap"].count == 1
    assert stats["OpenStreetMap"].height_sum_m == pytest.approx(9.0)
    assert stats["Microsoft ML Buildings"].count == 0
    total = sum(s.footprint_m2 for s in found.buildings)
    assert total == pytest.approx(100 + 50, rel=0.02)

    lon, lat = TO_WGS84.transform(SX + 105, SY + 105)
    tile = reader.building_tile(BRUSQUE, 16, *_tile(lon, lat, 16))
    assert tile  # MVT com o prédio
    assert reader.building_tile(BRUSQUE, 16, 0, 0) == b""


def _tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    import math  # noqa: PLC0415

    n = 2**z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def test_importing_another_city_keeps_brusque_layers(db: ConnectionPool) -> None:
    repo = PostgisTerritoryRepository(db)
    # mesmo lugar, outra cidade (só para o teste): as linhas de Brusque não podem sumir
    repo.replace(
        ITAPEMA,
        LayerData("setores", "IBGE", "u", "Fonte: IBGE",
                  tracts=[Tract("420830205000001", polygon(*TRACT), {"people": 7})]),
        WHEN,
    )  # fmt: skip
    with pytest.raises(ValueError, match="outra cidade"):
        repo.replace(
            ITAPEMA,
            LayerData("setores", "IBGE", "u", "Fonte: IBGE",
                      tracts=[Tract("420290905000009", polygon(*TRACT), {})]),
            WHEN,
        )  # fmt: skip
    reader = PostgisTerritoryReader(db)
    brusque = reader.overlaps(BRUSQUE, ring(*TRACT))
    itapema = reader.overlaps(ITAPEMA, ring(*TRACT))
    assert brusque is not None
    assert itapema is not None
    assert [t.code for t in brusque.tracts] == ["420290905000001"]
    assert [t.code for t in itapema.tracts] == ["420830205000001"]
    assert itapema.grid == []  # a grade e os valores de Brusque não vazam
    assert {r["layer"] for r in reader.layers(ITAPEMA)} == {"setores"}
    assert "declividade" in {r["layer"] for r in reader.layers(BRUSQUE)}
