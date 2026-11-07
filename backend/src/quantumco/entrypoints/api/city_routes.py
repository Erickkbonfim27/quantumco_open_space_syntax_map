"""Cidades na API: a lista do site e a cidade do caminho (`/api/v1/cities/{ibge_code}/…`)."""

# sem `from __future__ import annotations`: o FastAPI resolve os tipos em tempo de execução

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Path, Response

from quantumco.bootstrap.cities import LEGACY_CITY
from quantumco.road_network.application.queries import ListCities

CityCode = Annotated[
    str, Path(pattern=r"^\d{7}$", description="código IBGE do município (7 dígitos)")
]


def city_dependencies(cities: ListCities) -> tuple[Callable[..., str], Callable[[], str]]:
    """(cidade do caminho, conferida no catálogo; cidade das rotas antigas = Brusque)."""

    def path_city(ibge_code: CityCode) -> str:
        cities.published(ibge_code)  # NoCityError → 404
        return ibge_code

    def legacy_city() -> str:
        return LEGACY_CITY

    return path_city, legacy_city


def city_router(cities: ListCities) -> APIRouter:
    router = APIRouter(tags=["cidades"])

    @router.get("/cities")
    def list_cities(response: Response) -> list[dict[str, Any]]:
        """Cidades publicadas: nome, UF, endereço do mapa (/map/{uf}/{slug}) e enquadramento."""
        response.headers["Cache-Control"] = "public, max-age=60"
        return [city.to_json() for city in cities()]

    return router
