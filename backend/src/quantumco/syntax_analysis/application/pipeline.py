"""Etapa comum à análise oficial e aos cenários: retas do motor → NAIN/NACH por trecho."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.ports import EngineRun, FloatArray
from quantumco.syntax_analysis.domain.measures import nach, nain
from quantumco.syntax_analysis.domain.radius import Radius
from quantumco.syntax_analysis.domain.segmentation import Piece


def raw_link_measures(
    report_ids: Sequence[str],
    pieces: Sequence[Piece],
    piece_report_ids: Sequence[str],
    run: EngineRun,
    cfg: AnalysisConfig,
    *,
    radii: Sequence[Radius] | None = None,
) -> dict[str, FloatArray]:
    """NAIN e NACH por trecho (média ponderada pela extensão das retas), por raio.

    `piece_report_ids[i]` diz para qual trecho a reta i reporta (metades de um trecho dividido
    num cenário reportam o trecho original).
    """
    index = {rid: i for i, rid in enumerate(report_ids)}
    piece_link = np.array([index[rid] for rid in piece_report_ids])
    piece_len = np.array([p.length_m for p in pieces])
    size = len(report_ids)

    def to_links(values: FloatArray) -> FloatArray:
        ok = ~np.isnan(values)
        weighted = np.bincount(piece_link[ok], weights=values[ok] * piece_len[ok], minlength=size)
        weights = np.bincount(piece_link[ok], weights=piece_len[ok], minlength=size)
        out = np.full(size, np.nan)
        np.divide(weighted, weights, out=out, where=weights > 0)
        return out

    columns: dict[str, FloatArray] = {}
    for radius in radii or cfg.radii:
        raw = run.by_distance[radius.distance_m(cfg.radius_n_m)]
        columns[f"nain_{radius.key}"] = to_links(nain(raw.node_count, raw.total_depth))
        columns[f"nach_{radius.key}"] = to_links(nach(raw.choice, raw.total_depth))
    return columns
