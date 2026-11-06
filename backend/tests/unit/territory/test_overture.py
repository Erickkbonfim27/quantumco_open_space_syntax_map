from __future__ import annotations

from typing import Any

from pyproj import Transformer
from shapely import to_wkb
from shapely.geometry import LineString, Polygon

from quantumco.territory.domain.grid import BRUSQUE_GRID
from quantumco.territory.infrastructure.overture import grid_bbox, normalize_building

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


def test_grid_bbox_contains_every_grid_corner() -> None:
    west, south, east, north = grid_bbox()
    g = BRUSQUE_GRID
    for x in (g.west, g.east):
        for y in (g.south, g.north):
            lon, lat = TO_WGS84.transform(x, y)
            assert west <= lon <= east
            assert south <= lat <= north
