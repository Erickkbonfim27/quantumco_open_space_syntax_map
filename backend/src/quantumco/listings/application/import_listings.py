"""Carga de imóveis à venda (docs/adr/0003): atrás de feature flag, idempotente, registrada."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from quantumco.listings.application.ports import (
    FeatureDisabledError,
    FeatureFlags,
    ListingRepository,
    ListingSource,
    Rejection,
    RunTally,
    SourceBlockedError,
)
from quantumco.listings.domain.listing import SaleListing, SearchArea, problems

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImportReport:
    run_id: int
    source: str
    status: str
    tally: RunTally
    seconds: float


class ImportSaleListings:
    def __init__(
        self,
        flags: FeatureFlags,
        source: ListingSource,
        repository: ListingRepository,
        flag: str,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._flags = flags
        self._source = source
        self._repository = repository
        self._flag = flag
        self._clock = clock

    def __call__(self, area: SearchArea, max_pages: int = 40) -> ImportReport:
        if not self._flags.is_enabled(self._flag):
            raise FeatureDisabledError(
                f"flag '{self._flag}' desligada: ligue com `quantumco flags ligar {self._flag}`"
            )
        started = self._clock()
        source = self._source.name
        run_id = self._repository.start_run(area, source)
        log.info("carga %d: %s em %s (%s), até %d páginas",
                 run_id, source, area.city, area.ibge_code, max_pages)  # fmt: skip
        tally = RunTally()
        status, detail = "erro", ""
        try:
            for page in self._source.pages(area, max_pages):
                valid: list[SaleListing] = []
                rejected: list[Rejection] = []
                for item in page.listings:
                    reasons = problems(item, area)
                    if reasons:
                        rejected.append(Rejection(item, tuple(reasons)))
                    else:
                        valid.append(item)
                merged = self._repository.merge(run_id, area, valid)
                if rejected:
                    self._repository.reject(run_id, rejected)
                tally = replace(
                    tally,
                    pages=tally.pages + 1,
                    received=tally.received + len(page.listings),
                    new=tally.new + merged.new,
                    changed=tally.changed + merged.changed,
                    unchanged=tally.unchanged + merged.unchanged,
                    rejected=tally.rejected + len(rejected),
                    located=tally.located + sum(1 for item in valid if item.located),
                    attempts=tally.attempts + page.attempts,
                    total=page.total,
                    complete=page.last,
                )
                self._repository.progress(run_id, tally)
                log.info("  página %d: %d recebidos (%d novos, %d mudaram, %d iguais, "
                         "%d na quarentena), %d de %s, %d tentativa(s), %.1fs",
                         tally.pages, len(page.listings), merged.new, merged.changed,
                         merged.unchanged, len(rejected), tally.received, page.total,
                         page.attempts, self._clock() - started)  # fmt: skip
            if tally.complete:
                tally = replace(tally, removed=self._repository.mark_removed(run_id, area, source))
            else:
                log.warning("carga %d incompleta (limite de %d páginas): ninguém marcado como "
                            "removido", run_id, max_pages)  # fmt: skip
            status = "ok"
        except SourceBlockedError as exc:
            status, detail = "bloqueado", str(exc)
            tally = replace(tally, attempts=tally.attempts + exc.attempts)
            raise
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self._repository.finish_run(run_id, status, tally, detail)
            log.info("carga %d: %s em %.1fs", run_id, status, self._clock() - started)
        return ImportReport(run_id, source, status, tally, round(self._clock() - started, 1))
