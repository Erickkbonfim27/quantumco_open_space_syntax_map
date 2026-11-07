"""Cidade do cadastro: escolhida pelo código IBGE + relação do OSM, nunca pelo nome (Q14).

Existe "Brusque" na França e "Bom Jesus" em cinco estados; o código e a relação conferida pelo
`IBGE:GEOCODIGO` não deixam dúvida. Cada cidade guarda a faixa externa e o CRS com que foi
calculada, para o cálculo ser reproduzível mesmo se a regra da metodologia mudar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, replace
from enum import StrEnum

from quantumco.road_network.domain.study_area import StudyArea
from quantumco.shared_kernel.city import city_code

# As colunas de geometria do banco são tipadas em SIRGAS 2000 / UTM 22S (EPSG:31982), que cobre
# 54°W–48°W: Santa Catarina inteira e quase todo o PR e o RS. Abrir outras zonas exige soltar o
# SRID das colunas numa migração (docs/adr/0002-multi-cidade.md).
SUPPORTED_EPSG = frozenset({31982})


class CityStatus(StrEnum):
    PREPARING = "preparando"  # cadastrada; rede, análise ou território ainda em processamento
    PUBLISHED = "publicada"  # aparece no site


class UnsupportedCityError(ValueError):
    pass


def sirgas_utm_epsg(lon: float, lat: float) -> int:
    """EPSG do SIRGAS 2000 / UTM da zona que contém o ponto (zonas 18 a 25, as do Brasil)."""
    zone = int((lon + 180) // 6) + 1
    if not 18 <= zone <= 25:
        raise UnsupportedCityError(f"longitude {lon:.3f} fora das zonas UTM do Brasil (18–25)")
    return (31960 if lat < 0 else 31954) + zone


def slugify(name: str) -> str:
    """Nome em slug para a URL do mapa: "Balneário Camboriú" → "balneario-camboriu"."""
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    if not slug:
        raise UnsupportedCityError(f"nome sem letras para a URL: {name!r}")
    return slug


@dataclass(frozen=True, slots=True)
class City:
    ibge_code: str
    name: str
    uf: str
    slug: str
    osm_relation_id: int
    buffer_m: float
    crs_epsg: int
    status: CityStatus = CityStatus.PREPARING

    def __post_init__(self) -> None:
        object.__setattr__(self, "ibge_code", city_code(self.ibge_code))
        if not re.fullmatch(r"[A-Z]{2}", self.uf):
            raise UnsupportedCityError(f"UF inválida: {self.uf!r}")
        if self.crs_epsg not in SUPPORTED_EPSG:
            raise UnsupportedCityError(
                f"{self.name}-{self.uf} fica na EPSG:{self.crs_epsg}; por enquanto o banco só "
                "guarda cidades na UTM 22S (EPSG:31982). Veja docs/adr/0002-multi-cidade.md."
            )

    @classmethod
    def register(
        cls,
        *,
        ibge_code: str,
        name: str,
        uf: str,
        osm_relation_id: int,
        center: tuple[float, float],
        buffer_m: float,
    ) -> City:
        """Cidade nova a partir do diretório do IBGE e da relação do OSM (centro em lon/lat)."""
        lon, lat = center
        return cls(
            ibge_code=ibge_code,
            name=name.strip(),
            uf=uf.strip().upper(),
            slug=slugify(name),
            osm_relation_id=osm_relation_id,
            buffer_m=buffer_m,
            crs_epsg=sirgas_utm_epsg(lon, lat),
        )

    @property
    def label(self) -> str:
        return f"{self.name}-{self.uf}"

    def study_area(self) -> StudyArea:
        return StudyArea(
            ibge_code=self.ibge_code,
            osm_relation_id=self.osm_relation_id,
            buffer_m=self.buffer_m,
            crs_epsg=self.crs_epsg,
        )

    def published(self) -> City:
        return replace(self, status=CityStatus.PUBLISHED)
