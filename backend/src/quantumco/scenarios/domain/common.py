"""Regras comuns do contexto de cenários do usuário."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

# Brasil com folga (graus, WGS84): coordenada fora disso é erro de digitação ou de projeção.
BRAZIL = (-74.5, -34.5, -28.5, 6.0)


class InvalidWorkspaceError(ValueError):
    pass


def check_in_brazil(coords: Iterable[tuple[float, float]]) -> None:
    west, south, east, north = BRAZIL
    if not all(west <= x <= east and south <= y <= north for x, y in coords):
        raise InvalidWorkspaceError("Coordenadas fora do Brasil.")


@dataclass(frozen=True, slots=True)
class CityArea:
    """Onde um cenário da cidade pode desenhar: o município mais a faixa de cálculo (lon/lat)."""

    ibge_code: str
    name: str
    bounds: tuple[float, float, float, float]  # oeste, sul, leste, norte

    def check(self, coords: Iterable[tuple[float, float]], what: str) -> None:
        west, south, east, north = self.bounds
        if not all(west <= x <= east and south <= y <= north for x, y in coords):
            raise InvalidWorkspaceError(f"{what} precisa estar em {self.name} ou no entorno.")
