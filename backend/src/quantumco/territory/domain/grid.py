"""Grade fixa de 30 m para os dados raster (docs/specs/camadas-fase-b.md, §4.1).

Todas as camadas raster (MDT, MapBiomas, Sentinel, Landsat) são resumidas nesta mesma grade, em
SIRGAS 2000 / UTM 22S (EPSG:31982). Assim o recorte no polígono é sempre igual (centros de célula
dentro do polígono), e o MDT do SIGSC só sai daqui agregado, como pede a licença.

Uma grade por cidade (territory.grids), criada na primeira gravação e NUNCA mudada depois: o id
da célula é guardado no banco. Ela cobre a extensão dos setores do IBGE 2022 da cidade com 1 km de
folga, encaixada em múltiplos de 30 m (`grid_for_extent`). A de Brusque cobre 695.614–719.200 E,
6.983.650–7.011.993 N. Convenção de raster: linha 0 no norte, coluna 0 no oeste, e
id = linha × colunas + coluna. No banco só existem as células a até 1 km do município.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SRID = 31982
BUFFER_M = 1000.0  # folga em torno do município (células além disso não são gravadas)


@dataclass(frozen=True, slots=True)
class GridSpec:
    west: float
    north: float
    size: float
    ncols: int
    nrows: int

    def __post_init__(self) -> None:
        if self.size <= 0 or self.ncols <= 0 or self.nrows <= 0:
            raise ValueError("grade sem tamanho")

    @property
    def east(self) -> float:
        return self.west + self.ncols * self.size

    @property
    def south(self) -> float:
        return self.north - self.nrows * self.size

    @property
    def cells(self) -> int:
        return self.ncols * self.nrows

    def cell(self, col: int, row: int) -> int:
        if not (0 <= col < self.ncols and 0 <= row < self.nrows):
            raise ValueError(f"célula fora da grade: coluna {col}, linha {row}")
        return row * self.ncols + col

    def col_row(self, cell: int) -> tuple[int, int]:
        if not 0 <= cell < self.cells:
            raise ValueError(f"célula fora da grade: {cell}")
        row, col = divmod(cell, self.ncols)
        return col, row

    def center(self, cell: int) -> tuple[float, float]:
        col, row = self.col_row(cell)
        return self.west + (col + 0.5) * self.size, self.north - (row + 0.5) * self.size

    def locate(self, x: float, y: float) -> int | None:
        """Célula que contém o ponto (x, y) em EPSG:31982; None fora da grade.

        Bordas: a célula inclui os lados oeste e norte (o ponto no limite vai para leste/sul).
        """
        col = math.floor((x - self.west) / self.size)
        row = math.floor((self.north - y) / self.size)
        if 0 <= col < self.ncols and 0 <= row < self.nrows:
            return row * self.ncols + col
        return None


CELL_SIZE_M = 30.0


def grid_for_extent(
    xmin: float, ymin: float, xmax: float, ymax: float, *, size: float = CELL_SIZE_M
) -> GridSpec:
    """Grade de uma cidade: a extensão dos setores (no CRS métrico) + BUFFER_M, em múltiplos
    de `size`."""
    west = math.floor((xmin - BUFFER_M) / size) * size
    north = math.ceil((ymax + BUFFER_M) / size) * size
    ncols = math.ceil((xmax + BUFFER_M - west) / size)
    nrows = math.ceil((north - (ymin - BUFFER_M)) / size)
    return GridSpec(west=west, north=north, size=size, ncols=ncols, nrows=nrows)


BRUSQUE_GRID = GridSpec(west=694_590.0, north=7_013_010.0, size=30.0, ncols=854, nrows=1012)
CELL_AREA_M2 = CELL_SIZE_M**2
