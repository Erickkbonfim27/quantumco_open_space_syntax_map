from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from shapely.geometry import Polygon

from quantumco.road_network.domain.study_area import StudyArea
from quantumco.road_network.domain.topology import RoadLink
from quantumco.shared_kernel.events import DomainEvent
from quantumco.shared_kernel.ids import SnapshotId


class SnapshotInvariantError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CleaningReport:
    """Contagens que vão para o manifesto. Nada some sem ser contado."""

    ways_received: int
    ways_accepted: int
    rejected_by_reason: Mapping[str, int]
    links_total: int
    links_kept: int
    links_excluded_disconnected: int
    component_count: int
    length_total_m: float
    length_kept_m: float
    length_excluded_m: float

    def __post_init__(self) -> None:
        rejected = sum(self.rejected_by_reason.values())
        if self.ways_accepted + rejected != self.ways_received:
            raise SnapshotInvariantError("vias aceitas + rejeitadas ≠ vias recebidas")
        if self.links_kept + self.links_excluded_disconnected != self.links_total:
            raise SnapshotInvariantError("links mantidos + excluídos ≠ total")
        if not math.isclose(
            self.length_kept_m + self.length_excluded_m, self.length_total_m, rel_tol=1e-9
        ):
            raise SnapshotInvariantError("extensão mantida + excluída ≠ total")


@dataclass(frozen=True, slots=True, kw_only=True)
class SnapshotIngested(DomainEvent):
    snapshot_id: SnapshotId
    osm_base_timestamp: datetime
    links_kept: int


@dataclass(slots=True)
class NetworkSnapshot:
    """Agregado imutável (Q52): a rede analisável numa data registrada."""

    snapshot_id: SnapshotId
    study_area: StudyArea
    filter_version: str
    osm_base_timestamp: datetime
    source: str
    created_at: datetime
    links: tuple[RoadLink, ...]
    excluded_links: tuple[RoadLink, ...]
    report: CleaningReport
    municipality: Polygon  # limite usado no recorte, no CRS da área
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.links:
            raise SnapshotInvariantError("snapshot sem links analisáveis")
        if self.osm_base_timestamp.tzinfo is None:
            raise SnapshotInvariantError("osm_base_timestamp precisa de fuso")
        if self.municipality.is_empty:
            raise SnapshotInvariantError("snapshot sem limite municipal")
        if len(self.links) != self.report.links_kept:
            raise SnapshotInvariantError("links não batem com o relatório")

    @classmethod
    def ingest(
        cls,
        *,
        study_area: StudyArea,
        filter_version: str,
        osm_base_timestamp: datetime,
        source: str,
        created_at: datetime,
        links: tuple[RoadLink, ...],
        excluded_links: tuple[RoadLink, ...],
        report: CleaningReport,
        municipality: Polygon,
    ) -> NetworkSnapshot:
        snapshot = cls(
            snapshot_id=SnapshotId.new(),
            study_area=study_area,
            filter_version=filter_version,
            osm_base_timestamp=osm_base_timestamp,
            source=source,
            created_at=created_at,
            links=links,
            excluded_links=excluded_links,
            report=report,
            municipality=municipality,
        )
        snapshot._events.append(
            SnapshotIngested(
                occurred_at=created_at,
                snapshot_id=snapshot.snapshot_id,
                osm_base_timestamp=osm_base_timestamp,
                links_kept=len(links),
            )
        )
        return snapshot

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
