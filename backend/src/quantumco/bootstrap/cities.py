"""Cidades: a ponte entre o cadastro (Rede Viária) e os outros contextos.

Os contextos só guardam o código IBGE. Aqui o cadastro vira o que cada um precisa: a área de
desenho dos cenários, o CRS das edições e o recorte das camadas territoriais.
"""

from __future__ import annotations

from quantumco.bootstrap.road_network import city_list_query
from quantumco.bootstrap.settings import Settings
from quantumco.road_network.application.queries import CityView, ListCities
from quantumco.scenarios.domain.common import CityArea
from quantumco.shared_kernel.city import city_code, expand_bbox
from quantumco.territory.domain.city import TerritoryCity

# Rotas antigas, sem cidade no caminho, respondem Brusque (o site antes de haver cidades).
LEGACY_CITY = "4202909"


def city_area(city: CityView) -> CityArea | None:
    if city.bbox is None:
        return None
    return CityArea(
        ibge_code=city.ibge_code, name=city.name, bounds=expand_bbox(city.bbox, city.buffer_m)
    )


class PublishedCityAreas:
    """`CityAreas` dos cenários: só cidades publicadas, com o município + a faixa de cálculo."""

    def __init__(self, cities: ListCities) -> None:
        self._cities = cities

    def area(self, ibge_code: str) -> CityArea | None:
        for city in self._cities():
            if city.ibge_code == ibge_code:
                return city_area(city)
        return None


class CityNotReadyError(LookupError):
    pass


def city_view(settings: Settings, ibge_code: str) -> CityView:
    """A cidade do cadastro (publicada ou não), com o retângulo do snapshot atual."""
    code = city_code(ibge_code)
    for city in city_list_query(settings)(published_only=False):
        if city.ibge_code == code:
            return city
    raise CityNotReadyError(
        f"cidade {code} fora do cadastro; rode `quantumco cidade adicionar {code}`"
    )


def territory_city(settings: Settings, ibge_code: str) -> TerritoryCity:
    """O recorte que as fontes do território precisam (exige o snapshot da cidade)."""
    city = city_view(settings, ibge_code)
    if city.bbox is None:
        raise CityNotReadyError(
            f"{city.name}-{city.uf} ainda não tem rede publicada: o limite municipal vem do "
            f"snapshot (`quantumco snapshot build --cidade {city.ibge_code}`)"
        )
    return TerritoryCity(ibge_code=city.ibge_code, name=city.name, uf=city.uf, bbox=city.bbox)
