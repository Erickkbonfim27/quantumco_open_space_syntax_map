from __future__ import annotations

from datetime import datetime

from quantumco.bootstrap.settings import Settings
from quantumco.road_network.application.build_snapshot import BuildSnapshot
from quantumco.road_network.application.queries import GetCurrentNetwork
from quantumco.road_network.infrastructure.file_network_reader import FileNetworkReader
from quantumco.road_network.infrastructure.file_snapshot_repository import (
    FileSnapshotRepository,
)
from quantumco.road_network.infrastructure.overpass_source import OverpassWaySource
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology
from quantumco.shared_kernel.clock import SystemClock


def build_snapshot_use_case(settings: Settings, as_of: datetime | None = None) -> BuildSnapshot:
    return BuildSnapshot(
        source=OverpassWaySource(
            url=settings.overpass_url, timeout_s=settings.overpass_timeout_s, as_of=as_of
        ),
        methodology=YamlMethodology(settings.methodology_dir),
        repository=FileSnapshotRepository(settings.data_dir / "snapshots"),
        clock=SystemClock(),
    )


def current_network_query(settings: Settings) -> GetCurrentNetwork:
    return GetCurrentNetwork(FileNetworkReader(settings.data_dir / "snapshots"))
