"""A cidade como identificador compartilhado entre os contextos: o código IBGE do município.

Cada contexto guarda só o código (7 dígitos); nome, limite e CRS ficam no cadastro da Rede Viária.
"""

from __future__ import annotations

import math
import re

_IBGE_MUNICIPALITY = re.compile(r"^\d{7}$")


class InvalidCityCodeError(ValueError):
    pass


def city_code(value: object) -> str:
    """Valida e normaliza um código IBGE de município ("4208302")."""
    text = str(value).strip()
    if not _IBGE_MUNICIPALITY.match(text):
        raise InvalidCityCodeError(f"código IBGE de município inválido: {value!r}")
    return text


_M_PER_DEG = 111_320.0


def expand_bbox(
    bbox: tuple[float, float, float, float], meters: float
) -> tuple[float, float, float, float]:
    """Estende um retângulo lon/lat (oeste, sul, leste, norte) por uma distância em metros."""
    west, south, east, north = bbox
    dlat = meters / _M_PER_DEG
    dlon = meters / (_M_PER_DEG * max(math.cos(math.radians((south + north) / 2)), 0.1))
    return (west - dlon, south - dlat, east + dlon, north + dlat)
