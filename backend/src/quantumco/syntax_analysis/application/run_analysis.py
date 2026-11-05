from __future__ import annotations

import logging
import time
from collections import defaultdict

import numpy as np

from quantumco.shared_kernel.clock import Clock
from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.ports import (
    AnalysisRepository,
    AnalysisResult,
    AngularAnalyzer,
    FloatArray,
    NetworkSnapshotSource,
)
from quantumco.syntax_analysis.domain.measures import nach, nain
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

    def __call__(self) -> tuple[AnalysisResult, str]:
        started = time.perf_counter()
        cfg = self._config
        network = self._source.latest()
        if network is None:
            raise NoSnapshotForAnalysisError("nenhum snapshot; rode `quantumco snapshot build`")
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
        run = self._analyzer.analyze(pieces, distances)
        engine_s = time.perf_counter() - t_engine
        log.info(
            "[3/4] %s %s: ok em %.1fs (%d nós no grafo, %d retas sem valor)",
            run.engine,
            run.engine_version,
            engine_s,
            run.graph_nodes,
            run.unmatched_pieces,
        )

        # agrega retas → trechos (média ponderada pela extensão)
        link_index = {link.link_id: i for i, link in enumerate(network.links)}
        piece_link = np.array([link_index[p.link_id] for p in pieces])
        piece_len = np.array([p.length_m for p in pieces])
        link_len = np.array([link.length_m for link in network.links])
        in_result = np.array([link.in_result_zone for link in network.links])

        def to_links(values: FloatArray) -> FloatArray:
            ok = ~np.isnan(values)
            weighted = np.bincount(
                piece_link[ok], weights=values[ok] * piece_len[ok], minlength=len(link_len)
            )
            weights = np.bincount(piece_link[ok], weights=piece_len[ok], minlength=len(link_len))
            out = np.full(len(link_len), np.nan)
            np.divide(weighted, weights, out=out, where=weights > 0)
            return out

        log.info("[4/4] NAIN/NACH, percentis ponderados por extensão e %d classes", cfg.classes)
        columns: dict[str, FloatArray] = {}
        summary: dict[str, dict[str, float]] = defaultdict(dict)
        for radius, distance in zip(cfg.radii, distances, strict=True):
            raw = run.by_distance[distance]
            for name, piece_values in (
                ("nain", nain(raw.node_count, raw.total_depth)),
                ("nach", nach(raw.choice, raw.total_depth)),
            ):
                values = to_links(piece_values)
                scoped = np.where(in_result, values, np.nan)
                percentile = length_weighted_percentile(scoped, link_len)
                key = f"{name}_{radius.key}"
                columns[key] = values
                columns[f"c_{key}"] = classify(percentile, cfg.classes)
                summary[key] = {
                    "min": float(np.nanmin(scoped)),
                    "median": float(np.nanmedian(scoped)),
                    "max": float(np.nanmax(scoped)),
                }

        manifest = {
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
        )
        location = self._repository.save(result)
        log.info("análise concluída em %.1fs → %s", time.perf_counter() - started, location)
        return result, location
