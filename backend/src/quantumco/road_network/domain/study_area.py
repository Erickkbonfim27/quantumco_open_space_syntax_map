from __future__ import annotations

import re
from dataclasses import dataclass

_IBGE_MUNICIPALITY = re.compile(r"^\d{7}$")


class InvalidStudyAreaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StudyArea:
    """Área de estudo identificada por código, nunca por nome (Q14).

    `buffer_m` é a faixa externa usada no cálculo para reduzir o efeito de borda;
    os resultados valem só dentro do município.
    """

    ibge_code: str
    osm_relation_id: int
    buffer_m: float
    crs_epsg: int

    def __post_init__(self) -> None:
        if not _IBGE_MUNICIPALITY.match(self.ibge_code):
            raise InvalidStudyAreaError(f"código IBGE inválido: {self.ibge_code!r}")
        if self.osm_relation_id <= 0:
            raise InvalidStudyAreaError("osm_relation_id deve ser positivo")
        if self.buffer_m < 0:
            raise InvalidStudyAreaError("buffer_m não pode ser negativo")
        if self.crs_epsg <= 0:
            raise InvalidStudyAreaError("crs_epsg deve ser positivo")
