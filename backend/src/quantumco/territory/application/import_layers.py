"""Caso de uso: importar (ou reimportar) as camadas territoriais das fontes abertas."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

from quantumco.shared_kernel.clock import Clock
from quantumco.territory.application.ports import LayerSource, TerritoryRepository

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImportReport:
    layer: str
    rows: int
    seconds: float


class ImportTerritory:
    def __init__(
        self, *, sources: Sequence[LayerSource], repository: TerritoryRepository, clock: Clock
    ) -> None:
        self._sources = list(sources)
        self._repository = repository
        self._clock = clock

    @property
    def names(self) -> list[str]:
        return [s.name for s in self._sources]

    def __call__(self, only: Sequence[str] | None = None) -> list[ImportReport]:
        chosen = [s for s in self._sources if not only or s.name in only]
        unknown = set(only or ()) - {s.name for s in self._sources}
        if unknown:
            raise ValueError(f"fonte desconhecida: {', '.join(sorted(unknown))} (há: {self.names})")
        reports: list[ImportReport] = []
        for i, source in enumerate(chosen, 1):
            started = time.perf_counter()
            log.info("[%d/%d] %s: baixando e normalizando…", i, len(chosen), source.name)
            for data in source.fetch():
                log.info(
                    "[%d/%d] %s → camada %s: %d registros; gravando…",
                    i, len(chosen), source.name, data.layer, data.rows,
                )  # fmt: skip
                t0 = time.perf_counter()
                self._repository.replace(data, self._clock.now())
                seconds = time.perf_counter() - t0
                log.info("[%d/%d] camada %s gravada em %.1fs", i, len(chosen), data.layer, seconds)
                reports.append(ImportReport(data.layer, data.rows, round(seconds, 1)))
            elapsed = time.perf_counter() - started
            log.info("[%d/%d] %s concluída em %.1fs", i, len(chosen), source.name, elapsed)
        return reports
