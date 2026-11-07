from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from quantumco.road_network.application.ports import (
    CityRegistry,
    MethodologyProvider,
    OsmWaySource,
    SnapshotRepository,
)
from quantumco.road_network.domain.highway_filter import FilterVariant
from quantumco.road_network.domain.snapshot import CleaningReport, NetworkSnapshot
from quantumco.road_network.domain.topology import (
    AcceptedWay,
    keep_largest_component,
    split_into_links,
)
from quantumco.shared_kernel.city import city_code
from quantumco.shared_kernel.clock import Clock

log = logging.getLogger(__name__)

_STAGES = 5


@contextmanager
def _stage(number: int, name: str) -> Iterator[None]:
    log.info("[%d/%d] %s…", number, _STAGES, name)
    started = time.perf_counter()
    yield
    log.info("[%d/%d] %s: ok (%.1fs)", number, _STAGES, name, time.perf_counter() - started)


@dataclass(frozen=True, slots=True)
class BuildSnapshotResult:
    snapshot: NetworkSnapshot
    location: str


class UnknownCityError(LookupError):
    pass


class BuildSnapshot:
    """Caso de uso: extrato do OSM → filtro → topologia → maior componente → snapshot."""

    def __init__(
        self,
        source: OsmWaySource,
        methodology: MethodologyProvider,
        repository: SnapshotRepository,
        clock: Clock,
        cities: CityRegistry,
    ) -> None:
        self._source = source
        self._methodology = methodology
        self._repository = repository
        self._clock = clock
        self._cities = cities

    def __call__(
        self, ibge_code: str, variant: FilterVariant = FilterVariant.BASE
    ) -> BuildSnapshotResult:
        started = time.perf_counter()
        city = self._cities.get(city_code(ibge_code))
        if city is None:
            raise UnknownCityError(
                f"cidade {ibge_code} fora do cadastro; "
                f"rode `quantumco cidade adicionar {ibge_code}`"
            )
        area = city.study_area()
        highway_filter = self._methodology.highway_filter()
        log.info(
            "%s: metodologia %s, filtro %s/%s, IBGE %s, relação OSM %d",
            city.label,
            self._methodology.version(),
            highway_filter.version,
            variant.value,
            area.ibge_code,
            area.osm_relation_id,
        )

        with _stage(1, "baixando o OSM"):
            extract = self._source.fetch(area)
            log.info("OSM base: %s", extract.osm_base_timestamp.isoformat())

        with _stage(2, f"filtrando {len(extract.ways)} vias"):
            accepted: list[AcceptedWay] = []
            rejected: Counter[str] = Counter()
            for way in extract.ways:
                zone = way.zone_within(extract.municipality)
                decision = highway_filter.decide(way.tags, zone, variant)
                if decision.accepted:
                    accepted.append(AcceptedWay(way=way, zone=zone))
                else:
                    rejected[decision.reason] += 1
            log.info("aceitas: %d, rejeitadas: %d", len(accepted), sum(rejected.values()))
            for reason, count in rejected.most_common(5):
                log.info("  rejeição %-40s %6d", reason, count)

        with _stage(3, "montando a topologia"):
            links = split_into_links(accepted)
            log.info("%d trechos entre cruzamentos", len(links))

        with _stage(4, "separando o maior componente conectado"):
            split = keep_largest_component(links)
            kept_m = sum(link.length_m for link in split.kept)
            excluded_m = sum(link.length_m for link in split.excluded)
            log.info(
                "%d componentes; mantidos %d trechos (%.1f km), excluídos %d (%.1f km)",
                split.component_count,
                len(split.kept),
                kept_m / 1000,
                len(split.excluded),
                excluded_m / 1000,
            )

        report = CleaningReport(
            ways_received=len(extract.ways),
            ways_accepted=len(accepted),
            rejected_by_reason=dict(sorted(rejected.items())),
            links_total=len(links),
            links_kept=len(split.kept),
            links_excluded_disconnected=len(split.excluded),
            component_count=split.component_count,
            length_total_m=kept_m + excluded_m,
            length_kept_m=kept_m,
            length_excluded_m=excluded_m,
        )
        snapshot = NetworkSnapshot.ingest(
            study_area=area,
            filter_version=f"{highway_filter.version}/{variant.value}",
            osm_base_timestamp=extract.osm_base_timestamp,
            source=extract.source,
            created_at=self._clock.now(),
            links=split.kept,
            excluded_links=split.excluded,
            municipality=extract.municipality,
            report=report,
        )

        with _stage(5, "gravando o snapshot"):
            location = self._repository.save(snapshot, self._methodology.version())

        log.info(
            "snapshot %s concluído em %.1fs", snapshot.snapshot_id, time.perf_counter() - started
        )
        return BuildSnapshotResult(snapshot=snapshot, location=location)
