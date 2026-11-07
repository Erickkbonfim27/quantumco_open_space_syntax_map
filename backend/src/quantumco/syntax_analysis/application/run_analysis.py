from __future__ import annotations

import logging
import time
from collections import defaultdict

import numpy as np

from quantumco.shared_kernel.clock import Clock
from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.pipeline import raw_link_measures
from quantumco.syntax_analysis.application.ports import (
    AnalysisRepository,
    AnalysisResult,
    AngularAnalyzer,
    FloatArray,
    NetworkSnapshotSource,
)
from quantumco.syntax_analysis.domain.percentiles import classify, length_weighted_percentile
from quantumco.syntax_analysis.domain.segmentation import explode

log = logging.getLogger(__name__)


class NoSnapshotForAnalysisError(LookupError):
    pass


class RunAnalysis:
    """Caso de uso: snapshot → retas → motor angular → NAIN/NACH por trecho → classes."""

    def __init__(
        self,
        source: NetworkSnapshotSource,
        analyzer: AngularAnalyzer,
        repository: AnalysisRepository,
        config: AnalysisConfig,
        clock: Clock,
    ) -> None:
        self._source = source
        self._analyzer = analyzer
        self._repository = repository
        self._config = config
        self._clock = clock

    def __call__(self, ibge_code: str) -> tuple[AnalysisResult, str]:
        started = time.perf_counter()
        cfg = self._config
        network = self._source.latest(ibge_code)
        if network is None:
            raise NoSnapshotForAnalysisError(
                f"a cidade {ibge_code} não tem snapshot; rode `quantumco snapshot build`"
            )
        log.info("[1/4] snapshot %s: %d trechos", network.snapshot_name, len(network.links))

        pieces = explode(network.links, cfg.simplification_m)
        log.info(
            "[2/4] simplificação de %.1f m e explosão em retas: %d retas",
            cfg.simplification_m,
            len(pieces),
        )

        distances = [r.distance_m(cfg.radius_n_m) for r in cfg.radii]
        log.info("[3/4] análise angular (%s) nos raios %s…", "motor", [r.key for r in cfg.radii])
        t_engine = time.perf_counter()
        run = self._analyzer.analyze(pieces, distances, crs_epsg=network.crs_epsg)
        engine_s = time.perf_counter() - t_engine
        log.info(
            "[3/4] %s %s: ok em %.1fs (%d nós no grafo, %d retas sem valor)",
            run.engine,
            run.engine_version,
            engine_s,
            run.graph_nodes,
            run.unmatched_pieces,
        )

        # retas → trechos (NAIN/NACH, média ponderada pela extensão). É a mesma conta dos
        # cenários (`pipeline.raw_link_measures`): comparar cenário com a base só faz sentido
        # se as duas passam pelo mesmo código.
        link_len = np.array([link.length_m for link in network.links])
        in_result = np.array([link.in_result_zone for link in network.links])
        measures = raw_link_measures(
            [link.link_id for link in network.links],
            pieces,
            [p.link_id for p in pieces],
            run,
            cfg,
        )

        log.info("[4/4] NAIN/NACH, percentis ponderados por extensão e %d classes", cfg.classes)
        columns: dict[str, FloatArray] = {}
        summary: dict[str, dict[str, float]] = defaultdict(dict)
        for radius in cfg.radii:
            for name in ("nain", "nach"):
                key = f"{name}_{radius.key}"
                values = measures[key]
                scoped = np.where(in_result, values, np.nan)
                percentile = length_weighted_percentile(scoped, link_len)
                columns[key] = values
                columns[f"c_{key}"] = classify(percentile, cfg.classes)
                summary[key] = {
                    "min": float(np.nanmin(scoped)),
                    "median": float(np.nanmedian(scoped)),
                    "max": float(np.nanmax(scoped)),
                }

        manifest = {
            "ibge_code": network.ibge_code,
            "crs_epsg": network.crs_epsg,
            "snapshot_id": network.snapshot_id,
            "snapshot_name": network.snapshot_name,
            "methodology_version": cfg.methodology_version,
            "preliminary": cfg.preliminary,
            "engine": run.engine,
            "engine_version": run.engine_version,
            "radii": [r.key for r in cfg.radii],
            "radius_n_m": cfg.radius_n_m,
            "simplification_m": cfg.simplification_m,
            "classes": cfg.classes,
            "links": len(network.links),
            "pieces": len(pieces),
            "graph_nodes": run.graph_nodes,
            "unmatched_pieces": run.unmatched_pieces,
            "engine_seconds": round(engine_s, 1),
            "created_at": self._clock.now().isoformat(),
            "summary_result_zone": dict(summary),
        }
        result = AnalysisResult(
            snapshot_id=network.snapshot_id,
            snapshot_name=network.snapshot_name,
            link_ids=tuple(link.link_id for link in network.links),
            columns=columns,
            manifest=manifest,
            ibge_code=network.ibge_code,
        )
        location = self._repository.save(result)
        log.info("análise concluída em %.1fs → %s", time.perf_counter() - started, location)
        return result, location
