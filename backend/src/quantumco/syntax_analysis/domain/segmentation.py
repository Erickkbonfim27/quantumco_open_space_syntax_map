"""Formato único de produção (Q47): simplificação Douglas-Peucker e explosão em retas."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from shapely.geometry import LineString

Coords = tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class Link:
    link_id: str
    coords: Coords
    in_result_zone: bool

    @property
    def length_m(self) -> float:
        return float(LineString(self.coords).length)


@dataclass(frozen=True, slots=True)
class Piece:
    """Reta que entra no motor. Pertence a um único trecho."""

    piece_id: str
    link_id: str
    start: tuple[float, float]
    end: tuple[float, float]

    @property
    def length_m(self) -> float:
        (x1, y1), (x2, y2) = self.start, self.end
        return float(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5)


def explode(links: Iterable[Link], tolerance_m: float) -> list[Piece]:
    """Simplifica cada trecho (as pontas são preservadas) e quebra em retas."""
    pieces: list[Piece] = []
    for link in links:
        line = LineString(link.coords)
        simplified = (
            line.simplify(tolerance_m, preserve_topology=False) if tolerance_m > 0 else line
        )
        if not isinstance(simplified, LineString):  # DP numa linha sempre devolve LineString
            simplified = line
        coords: Sequence[tuple[float, float]] = [(float(x), float(y)) for x, y in simplified.coords]
        k = 0
        for start, end in itertools.pairwise(coords):
            if start == end:
                continue
            pieces.append(Piece(f"{link.link_id}#{k}", link.link_id, start, end))
            k += 1
    return pieces
