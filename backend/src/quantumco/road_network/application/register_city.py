"""Caso de uso: cadastrar uma cidade a partir do código IBGE (`quantumco cidade adicionar`)."""

from __future__ import annotations

import logging

from quantumco.road_network.application.ports import (
    BoundaryLocator,
    CityRegistry,
    MethodologyProvider,
    MunicipalityDirectory,
)
from quantumco.road_network.domain.city import City
from quantumco.shared_kernel.city import city_code

log = logging.getLogger(__name__)


class CityNotFoundError(LookupError):
    pass


class RegisterCity:
    def __init__(
        self,
        *,
        registry: CityRegistry,
        directory: MunicipalityDirectory,
        boundaries: BoundaryLocator,
        methodology: MethodologyProvider,
    ) -> None:
        self._registry = registry
        self._directory = directory
        self._boundaries = boundaries
        self._methodology = methodology

    def __call__(self, ibge_code: str) -> tuple[City, bool]:
        """Devolve a cidade e se ela é nova (cadastrar de novo não muda nada)."""
        code = city_code(ibge_code)
        existing = self._registry.get(code)
        if existing is not None:
            log.info("%s (%s) já está no cadastro: %s", existing.label, code, existing.status)
            return existing, False
        municipality = self._directory.lookup(code)
        if municipality is None:
            raise CityNotFoundError(f"o IBGE não tem município com o código {code}")
        boundary = self._boundaries.find(code)
        if boundary is None:
            raise CityNotFoundError(
                f"o OSM não tem relação de limite com IBGE:GEOCODIGO={code} "
                f"({municipality.name}-{municipality.uf})"
            )
        city = City.register(
            ibge_code=code,
            name=municipality.name,
            uf=municipality.uf,
            osm_relation_id=boundary.osm_relation_id,
            center=boundary.center,
            buffer_m=self._methodology.buffer_m(),
        )
        self._registry.add(city)
        log.info(
            "cadastrada: %s (IBGE %s, relação OSM %d, EPSG:%d, faixa de %.0f km)",
            city.label,
            code,
            city.osm_relation_id,
            city.crs_epsg,
            city.buffer_m / 1000,
        )
        return city, True
