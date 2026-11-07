"""Processar uma cidade de ponta a ponta: rede do OSM → análise sintática → território → publica.

Roda pela CLI (`quantumco cidade processar`) ou na fila `dados` (job `process_city`). Cada etapa
registra início, fim e tempo no log; a cidade só aparece no site no fim, se tudo deu certo.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any

from quantumco.bootstrap.cities import territory_city
from quantumco.bootstrap.road_network import build_snapshot_use_case, city_registry
from quantumco.bootstrap.settings import Settings
from quantumco.bootstrap.syntax_analysis import run_analysis_use_case
from quantumco.bootstrap.territory import import_territory_use_case
from quantumco.platform.postgres import shared_pool
from quantumco.road_network.application.build_snapshot import UnknownCityError
from quantumco.road_network.domain.city import CityStatus
from quantumco.shared_kernel.city import city_code

log = logging.getLogger(__name__)

CITY_JOB = "quantumco.entrypoints.worker.jobs.process_city"


def process_city(
    settings: Settings,
    ibge_code: str,
    *,
    territory: bool = True,
    only: Sequence[str] | None = None,
) -> dict[str, Any]:
    """`territory=False` pula as camadas (só rede e sintaxe); `only` limita as fontes delas."""
    code = city_code(ibge_code)
    city = city_registry(settings).get(code)
    if city is None:
        raise UnknownCityError(f"cidade {code} fora do cadastro; rode `quantumco cidade adicionar`")
    started = time.perf_counter()
    steps = 4 if territory else 3
    summary: dict[str, Any] = {"ibge_code": code, "city": city.label}
    log.info("=== %s (IBGE %s): processamento em %d etapas ===", city.label, code, steps)

    t0 = time.perf_counter()
    log.info("[1/%d] rede viária do OSM…", steps)
    snapshot = build_snapshot_use_case(settings)(code).snapshot
    summary["snapshot_id"] = str(snapshot.snapshot_id)
    summary["links"] = snapshot.report.links_kept
    summary["km"] = round(snapshot.report.length_kept_m / 1000, 1)
    log.info("[1/%d] rede: ok em %.1fs", steps, time.perf_counter() - t0)

    t0 = time.perf_counter()
    log.info("[2/%d] análise sintática (todos os raios)…", steps)
    analysis, _ = run_analysis_use_case(settings)(code)
    summary["engine_seconds"] = analysis.manifest["engine_seconds"]
    log.info("[2/%d] análise: ok em %.1fs", steps, time.perf_counter() - t0)

    if territory:
        t0 = time.perf_counter()
        log.info("[3/%d] camadas do território…", steps)
        try:
            reports = import_territory_use_case(settings)(territory_city(settings, code), only)
        finally:
            shared_pool(settings.require_database()).close()
        summary["layers"] = {r.layer: r.rows for r in reports}
        log.info("[3/%d] território: ok em %.1fs", steps, time.perf_counter() - t0)

    log.info("[%d/%d] publicando %s no site…", steps, steps, city.label)
    city_registry(settings).set_status(code, CityStatus.PUBLISHED)
    summary["seconds"] = round(time.perf_counter() - started, 1)
    log.info("=== %s publicada em %.1fs ===", city.label, summary["seconds"])
    return summary
