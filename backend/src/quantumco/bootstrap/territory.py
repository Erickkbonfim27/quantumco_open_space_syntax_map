from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import pool
from quantumco.shared_kernel.clock import SystemClock
from quantumco.territory.application.import_layers import ImportTerritory
from quantumco.territory.application.queries import GetPolygonProfile
from quantumco.territory.infrastructure.cnes import CnesSource
from quantumco.territory.infrastructure.ibge import CensusTractsSource, CnefeSource
from quantumco.territory.infrastructure.postgis_territory import (
    PostgisTerritoryReader,
    PostgisTerritoryRepository,
)
from quantumco.territory.infrastructure.sgb import SgbSource


def import_territory_use_case(settings: Settings) -> ImportTerritory:
    cache = settings.cache_dir / "territory"
    return ImportTerritory(
        # CNEFE antes dos setores não importa: o peso dasimétrico é calculado na consulta
        sources=[CensusTractsSource(cache), CnefeSource(cache), SgbSource(), CnesSource()],
        repository=PostgisTerritoryRepository(pool(settings.require_database(), max_size=2)),
        clock=SystemClock(),
    )


def territory_profile_query(settings: Settings) -> GetPolygonProfile:
    return GetPolygonProfile(PostgisTerritoryReader(pool(settings.require_database(), max_size=3)))
