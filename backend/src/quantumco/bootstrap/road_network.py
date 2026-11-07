from __future__ import annotations

from datetime import datetime

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import shared_pool
from quantumco.road_network.application.build_snapshot import BuildSnapshot
from quantumco.road_network.application.queries import GetCurrentNetwork, ListCities
from quantumco.road_network.application.register_city import RegisterCity
from quantumco.road_network.infrastructure.ibge_localidades import IbgeMunicipalityDirectory
from quantumco.road_network.infrastructure.overpass_source import OverpassWaySource
from quantumco.road_network.infrastructure.postgis_cities import (
    PostgisCityCatalog,
    PostgisCityRegistry,
)
from quantumco.road_network.infrastructure.postgis_network_reader import PostgisNetworkReader
from quantumco.road_network.infrastructure.postgis_snapshot_repository import (
    PostgisSnapshotRepository,
)
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology
from quantumco.shared_kernel.clock import SystemClock


def _overpass(settings: Settings, as_of: datetime | None = None) -> OverpassWaySource:
    return OverpassWaySource(
        url=settings.overpass_url, timeout_s=settings.overpass_timeout_s, as_of=as_of
    )


def city_registry(settings: Settings) -> PostgisCityRegistry:
    return PostgisCityRegistry(settings.require_database())


def build_snapshot_use_case(settings: Settings, as_of: datetime | None = None) -> BuildSnapshot:
    return BuildSnapshot(
        source=_overpass(settings, as_of),
        methodology=YamlMethodology(settings.methodology_dir),
        repository=PostgisSnapshotRepository(settings.require_database()),
        clock=SystemClock(),
        cities=city_registry(settings),
    )


def register_city_use_case(settings: Settings) -> RegisterCity:
    return RegisterCity(
        registry=city_registry(settings),
        directory=IbgeMunicipalityDirectory(),
        boundaries=_overpass(settings),
        methodology=YamlMethodology(settings.methodology_dir),
    )


def current_network_query(settings: Settings) -> GetCurrentNetwork:
    return GetCurrentNetwork(PostgisNetworkReader(shared_pool(settings.require_database())))


def city_list_query(settings: Settings) -> ListCities:
    return ListCities(PostgisCityCatalog(shared_pool(settings.require_database())))
