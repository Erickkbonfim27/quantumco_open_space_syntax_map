"""Fase B (spec §4): resumo da grade de 30 m, edificações, imagens e tiles."""

from __future__ import annotations

import pytest

from quantumco.territory.application.queries import (
    BUILDING_MIN_ZOOM,
    GetPolygonProfile,
    InvalidTileError,
    UnknownLayerError,
)
from quantumco.territory.domain import profile
from quantumco.territory.domain.profile import BuildingStats, GridStat
from quantumco.territory.domain.records import (
    Building,
    GridKind,
    GridLayer,
    LayerData,
    LegendItem,
    RasterImage,
)

from ...fakes import TINY_PNG, TerritoryReader


def test_grid_continuous_layer_keeps_stats_and_coverage() -> None:
    stat = GridStat("ndvi", "continuous", 10, mean=0.4123456, minimum=0.1, maximum=0.8,
                    p10=0.2, p50=0.4, p90=0.7)  # fmt: skip
    out = profile.grid([stat], area_m2=18_000, cell_area_m2=900)
    assert out["ndvi"]["coverage"] == 0.5  # 10 células × 900 m² ÷ 18.000 m²
    assert out["ndvi"]["mean"] == 0.4123
    assert out["ndvi"]["p90"] == 0.7
    assert "shares" not in out["ndvi"]


def test_grid_categorical_layer_reports_shares_by_class() -> None:
    stat = GridStat("mb_classe", "categorical", 4, histogram={24.0: 3, 3.0: 1})
    out = profile.grid([stat], area_m2=1_000, cell_area_m2=900)
    assert out["mb_classe"]["shares"] == {"24": 0.75, "3": 0.25}
    assert list(out["mb_classe"]["shares"]) == ["24", "3"]  # maior fatia primeiro
    assert out["mb_classe"]["coverage"] == 1.0  # nunca passa de 100%
    assert "mean" not in out["mb_classe"]


def test_grid_skips_layers_without_cells_inside() -> None:
    assert profile.grid([GridStat("lst", "continuous", 0)], 500, 900) == {}


def test_buildings_none_means_not_imported_and_zero_means_none_inside() -> None:
    assert profile.buildings(None, 1_000) is None
    empty = profile.buildings([], 1_000)
    assert empty is not None
    assert empty["count"] == 0
    assert empty["mean_height_m"] is None
    assert empty["with_height_share"] is None


def test_buildings_coverage_height_and_sources() -> None:
    out = profile.buildings(
        [
            BuildingStats("OpenStreetMap", 40, 30_000, 10, 65.0),
            BuildingStats("Microsoft ML Buildings", 160, 90_000, 0, 0.0),
        ],
        area_m2=1_000_000,
    )
    assert out is not None
    assert out["count"] == 200
    assert out["coverage_ratio"] == 0.12
    assert out["with_height_share"] == 0.05
    assert out["mean_height_m"] == 6.5  # só dos 10 prédios com altura
    assert list(out["by_source"]) == ["Microsoft ML Buildings", "OpenStreetMap"]


def test_layer_rows_count_grid_cells_and_buildings() -> None:
    square = {"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}
    data = LayerData(
        layer="edificacoes", source="Overture", source_url="https://overturemaps.org",
        license="ODbL", buildings=[Building("a", "OpenStreetMap", square)],
    )  # fmt: skip
    assert data.rows == 1
    grid = GridLayer(GridKind.CONTINUOUS, {1: 2.0, 2: 3.0}, unit="%")
    assert LayerData("declividade", "SIGSC", "u", "l", grid=grid).rows == 2


def test_raster_image_must_be_png_with_ordered_bounds() -> None:
    ok = RasterImage(TINY_PNG, (-49.1, -27.3, -48.7, -26.9), [LegendItem("> 30%", "#FF6B5E")])
    assert ok.legend[0].color == "#FF6B5E"
    with pytest.raises(ValueError, match="PNG"):
        RasterImage(b"GIF89a", (-49.1, -27.3, -48.7, -26.9))
    with pytest.raises(ValueError, match="invertidos"):
        RasterImage(TINY_PNG, (-48.7, -27.3, -49.1, -26.9))


def test_low_zoom_building_tiles_are_empty_without_touching_the_reader() -> None:
    reader = TerritoryReader()
    query = GetPolygonProfile(reader)
    assert query.building_tile(BUILDING_MIN_ZOOM - 1, 0, 0) == b""
    assert reader.tiles == []
    assert query.building_tile(14, 6000, 9000) == b"\x1a\x02mvt"
    assert reader.tiles == [(14, 6000, 9000)]


@pytest.mark.parametrize(("z", "x", "y"), [(-1, 0, 0), (23, 0, 0), (14, 16384, 0), (14, 0, -1)])
def test_invalid_tiles_are_rejected(z: int, x: int, y: int) -> None:
    with pytest.raises(InvalidTileError):
        GetPolygonProfile(TerritoryReader()).building_tile(z, x, y)


def test_image_layer_names_are_validated() -> None:
    query = GetPolygonProfile(TerritoryReader())
    assert query.image("declividade") == TINY_PNG
    assert query.image("ndvi") is None
    with pytest.raises(UnknownLayerError):
        query.image("../segredo")
