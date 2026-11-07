from __future__ import annotations

from typing import Any

import pytest
from pyproj import Transformer
from shapely import to_wkb
from shapely.geometry import LineString, Point, Polygon

from quantumco.territory.domain.city import TerritoryCity
from quantumco.territory.infrastructure.overture import (
    city_bbox,
    normalize_building,
    normalize_place,
)

TO_WGS84 = Transformer.from_crs(31982, 4326, always_xy=True)


def square(side_m: float) -> bytes:
    x, y = 700_000.0, 7_000_000.0
    corners = [(x, y), (x + side_m, y), (x + side_m, y + side_m), (x, y + side_m)]
    return to_wkb(Polygon([TO_WGS84.transform(*c) for c in corners]))


def row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "fe71",
        "geometry": square(10),
        "sources": [
            {"property": "/properties/height", "dataset": "OpenStreetMap"},
            {"property": "", "dataset": "Google Open Buildings", "confidence": 0.85},
        ],
        "is_underground": False,
        "height": None,
        "num_floors": 2,
        "class": "house",
    }
    return base | over


def test_building_keeps_whole_feature_source_and_confidence() -> None:
    b, why = normalize_building(row())
    assert why == "ok"
    assert b is not None
    assert b.source == "Google Open Buildings"  # não a fonte só da altura
    assert b.confidence == 0.85
    assert (b.floors, b.klass, b.height_m) == (2, "house", None)
    assert b.geometry["type"] == "Polygon"


def test_small_underground_and_non_polygonal_are_discarded_with_reason() -> None:
    assert normalize_building(row(geometry=square(3)))[1] == "pequeno"  # 9 m² < 10 m²
    assert normalize_building(row(is_underground=True))[1] == "subterraneo"
    line = to_wkb(LineString([(-48.9, -27.1), (-48.89, -27.1)]))
    assert normalize_building(row(geometry=line))[1] == "geometria"


def test_source_falls_back_to_first_cited_dataset() -> None:
    b, _ = normalize_building(row(sources=[{"property": "/x", "dataset": "OpenStreetMap"}]))
    assert b is not None
    assert b.source == "OpenStreetMap"
    assert b.confidence is None
    b, _ = normalize_building(row(sources=None))
    assert b is not None
    assert b.source == "desconhecida"


def place_row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "3fd5",
        "geometry": to_wkb(Point(-48.92, -27.10)),
        "confidence": 0.97,
        "operating_status": None,
        "names": {"primary": "Restaurante Mesa do Colono"},
        "taxonomy": {"primary": "restaurant", "hierarchy": ["food_and_drink", "restaurant"]},
        "sources": [{"property": "", "dataset": "meta", "license": "CDLA-Permissive-2.0"}],
    }
    return base | over


def test_place_keeps_group_category_and_license_only() -> None:
    p, why = normalize_place(place_row())
    assert why == "ok"
    assert p is not None
    assert (p.layer, p.kind, p.name) == ("lugares", "alimentacao", "Restaurante Mesa do Colono")
    assert dict(p.attrs) == {
        "category": "restaurant",
        "confidence": 0.97,
        "source": "meta",
        "license": "CDLA-Permissive-2.0",
    }
    assert (p.lon, p.lat) == (-48.92, -27.10)


def test_places_below_confidence_closed_or_ungrouped_are_discarded() -> None:
    assert normalize_place(place_row(confidence=0.49))[1] == "baixa_confianca"
    assert normalize_place(place_row(operating_status="permanently_closed"))[1] == "fechado"
    river = {"primary": "river", "hierarchy": ["geographic_entities", "river"]}
    assert normalize_place(place_row(taxonomy=river))[1] == "sem_grupo"
    assert normalize_place(place_row(taxonomy=None))[1] == "sem_grupo"


def test_importing_the_cli_does_not_open_proj() -> None:
    """O worker faz fork depois de importar a CLI: PROJ aberto no pai derruba o filho no macOS."""
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    code = (
        "import quantumco.entrypoints.cli.main\n"
        "from quantumco.territory.infrastructure import overture as o\n"
        "print(o._to_utm.cache_info().currsize)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, timeout=120
    )
    assert out.stdout.strip() == "0"


def test_city_bbox_is_the_municipality_with_the_grid_margin() -> None:
    itapema = TerritoryCity("4208302", "Itapema", "SC", (-48.690, -27.151, -48.584, -27.048))
    west, south, east, north = city_bbox(itapema)
    # 1 km ≈ 0,009° de latitude e ≈ 0,010° de longitude nessa latitude
    assert south == pytest.approx(-27.151 - 0.009, abs=1e-3)
    assert north == pytest.approx(-27.048 + 0.009, abs=1e-3)
    assert west == pytest.approx(-48.690 - 0.0101, abs=1e-3)
    assert east == pytest.approx(-48.584 + 0.0101, abs=1e-3)
