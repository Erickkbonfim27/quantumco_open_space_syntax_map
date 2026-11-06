from __future__ import annotations

import pytest

from quantumco.territory.domain.grid import BRUSQUE_GRID, BUFFER_M, CELL_AREA_M2, GridSpec

# extensão dos setores do IBGE 2022 de Brusque em EPSG:31982 (lida do PostGIS em 2026-11-06)
TRACTS = (695_613.79, 6_983_650.32, 719_200.49, 7_011_992.54)


def test_brusque_grid_is_frozen() -> None:
    # o id da célula é gravado no banco: mudar a grade exige migração (spec §4.1)
    assert (BRUSQUE_GRID.west, BRUSQUE_GRID.north) == (694_590.0, 7_013_010.0)
    assert (BRUSQUE_GRID.ncols, BRUSQUE_GRID.nrows, BRUSQUE_GRID.size) == (854, 1012, 30.0)
    assert BRUSQUE_GRID.cells == 864_248
    assert CELL_AREA_M2 == 900.0


def test_brusque_grid_covers_the_municipality_with_buffer_on_a_30m_lattice() -> None:
    g = BRUSQUE_GRID
    for edge in (g.west, g.south, g.east, g.north):
        assert edge % 30 == 0
    xmin, ymin, xmax, ymax = TRACTS
    assert g.west <= xmin - BUFFER_M
    assert g.south <= ymin - BUFFER_M
    assert g.east >= xmax + BUFFER_M
    assert g.north >= ymax + BUFFER_M
    # e sem sobra além de uma célula em cada lado
    assert xmin - BUFFER_M - g.west < 30
    assert g.north - (ymax + BUFFER_M) < 30


def test_cell_ids_follow_raster_order_north_to_south() -> None:
    g = GridSpec(west=0, north=90, size=30, ncols=4, nrows=3)
    assert g.cell(0, 0) == 0
    assert g.cell(3, 0) == 3
    assert g.cell(0, 1) == 4
    assert g.col_row(11) == (3, 2)
    assert g.center(0) == (15.0, 75.0)  # canto noroeste
    assert g.center(11) == (105.0, 15.0)  # canto sudeste


def test_locate_round_trips_with_center_and_handles_edges() -> None:
    g = BRUSQUE_GRID
    for cell in (0, 1, 853, 854, 500_000, g.cells - 1):
        assert g.locate(*g.center(cell)) == cell
    assert g.locate(g.west, g.north) == 0  # canto noroeste pertence à primeira célula
    assert g.locate(g.west + 30, g.north - 0.01) == 1
    assert g.locate(g.east, g.north - 1) is None  # borda leste fica fora
    assert g.locate(g.west - 0.01, g.north - 1) is None
    assert g.locate(g.west + 1, g.south) is None  # borda sul fica fora


def test_out_of_range_cells_are_rejected() -> None:
    g = GridSpec(west=0, north=60, size=30, ncols=2, nrows=2)
    with pytest.raises(ValueError, match="fora da grade"):
        g.cell(2, 0)
    with pytest.raises(ValueError, match="fora da grade"):
        g.col_row(4)
    with pytest.raises(ValueError, match="sem tamanho"):
        GridSpec(west=0, north=0, size=30, ncols=0, nrows=1)
