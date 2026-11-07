"""A cidade como o território precisa dela: código, nome, UF e o retângulo do município.

O cadastro fica na Rede Viária; o bootstrap entrega este recorte às fontes e ao banco.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from quantumco.shared_kernel.city import city_code, expand_bbox


@dataclass(frozen=True, slots=True)
class TerritoryCity:
    ibge_code: str
    name: str
    uf: str
    bbox: tuple[float, float, float, float]  # limite municipal, lon/lat (oeste, sul, leste, norte)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ibge_code", city_code(self.ibge_code))

    @property
    def state_code(self) -> str:
        """Código IBGE da UF (2 primeiros dígitos): "42" = SC."""
        return self.ibge_code[:2]

    @property
    def short_code(self) -> str:
        """Código de 6 dígitos (sem o verificador), usado pelo DATASUS."""
        return self.ibge_code[:6]

    @property
    def label(self) -> str:
        return f"{self.name}-{self.uf}"

    def upper_name(self, *, accents: bool = True) -> str:
        """Nome em maiúsculas, como o SGB grava ("BALNEÁRIO CAMBORIÚ")."""
        upper = self.name.upper()
        if accents:
            return upper
        return unicodedata.normalize("NFKD", upper).encode("ascii", "ignore").decode()

    def around(self, meters: float) -> tuple[float, float, float, float]:
        return expand_bbox(self.bbox, meters)

    def contains(self, lon: float, lat: float, margin_m: float) -> bool:
        west, south, east, north = self.around(margin_m)
        return west <= lon <= east and south <= lat <= north
