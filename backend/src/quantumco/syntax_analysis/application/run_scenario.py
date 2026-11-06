"""Caso de uso: cenário "e se…" sobre a análise publicada (laboratório, Q23).

Recalcula os raios escolhidos com o mesmo motor e a mesma metodologia da análise oficial, e
compara trecho a trecho com a base. Com o raio n, a cidade inteira; sem ele, só a região que a
edição pode alterar, com resultado igual ao da cidade inteira (domain/scope.py). As classes do
cenário usam os CORTES DA BASE, para que ganhos e perdas fiquem visíveis (percentis do próprio
cenário reescalonariam tudo e esconderiam o efeito).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from quantumco.shared_kernel.clock import Clock
from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.pipeline import raw_link_measures
from quantumco.syntax_analysis.application.ports import (
    AngularAnalyzer,
    BaseAnalysis,
    BaseAnalysisSource,
    FloatArray,
    ScenarioRepository,
    ScenarioResult,
)
from quantumco.syntax_analysis.domain.edits import AddStreet, Edit, RemoveLink, apply_edits
from quantumco.syntax_analysis.domain.percentiles import class_cutoffs, classify_by_cutoffs
from quantumco.syntax_analysis.domain.scope import Region, affected_region, check_radii, is_local
from quantumco.syntax_analysis.domain.segmentation import explode

log = logging.getLogger(__name__)

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
SUMMARY_KEYS = ("nain_n", "nach_n", "nain_800", "nach_800")


class NoBaseAnalysisError(LookupError):
    pass


class RunScenario:
    def __init__(
        self,
        *,
        base: BaseAnalysisSource,
        analyzer: AngularAnalyzer,
        repository: ScenarioRepository,
        config: AnalysisConfig,
        clock: Clock,
        snap_tolerance_m: float = 30.0,
    ) -> None:
        self._base = base
        self._analyzer = analyzer
        self._repository = repository
        self._config = config
        self._clock = clock
        self._snap = snap_tolerance_m

    def __call__(
        self,
        name: str,
        edits: Sequence[Edit],
        on_stage: Callable[[str], None] | None = None,
        radii: Sequence[str] | None = None,
    ) -> tuple[ScenarioResult, str]:
        """`on_stage` recebe loading, editing, engine, comparing e saving, nessa ordem.

        `radii`: chaves dos raios a recalcular (padrão: todos). Sem "n", só a região que a edição
        pode alterar é recalculada (exato; ver domain/scope.py) e o resto fica com a base.
        """
        if not _NAME.match(name):
            raise ValueError("nome do cenário: minúsculas, números e hífen (ex.: ponte-centro)")
        if not edits:
            raise ValueError("cenário sem edições")
        stage = on_stage or (lambda _: None)
        started = time.perf_counter()
        cfg = self._config
        keys = check_radii(radii or [r.key for r in cfg.radii], [r.key for r in cfg.radii])
        selected = tuple(r for r in cfg.radii if r.key in keys)
        local = is_local(keys)
        stage("loading")
        base = self._base.current()
        if base is None:
            raise NoBaseAnalysisError("nenhuma análise publicada; rode `quantumco coldstart`")
        log.info("[1/4] base %s: %d trechos", base.analysis_id, len(base.links))

        stage("editing")
        edited = apply_edits(base.links, edits, self._snap)
        log.info(
            "[2/4] edições: %d removidos, %d novos, encaixes a %s m",
            len(edited.removed),
            len(edited.added),
            edited.snaps_m,
        )

        pieces = explode(edited.links, cfg.simplification_m)
        report_of_piece = [edited.report_id(p.link_id) for p in pieces]
        base_ids = [link.link_id for link in base.links]
        report_ids = [rid for rid in base_ids if rid not in set(edited.removed)] + edited.added

        distances = [r.distance_m(cfg.radius_n_m) for r in selected]
        region: Region | None = None
        if local:
            changed = [link.coords for link in base.links if link.link_id in set(edited.removed)]
            changed += [
                link.coords
                for link in edited.links
                if link.link_id in set(edited.added) or link.link_id in edited.origin
            ]
            link_report_ids = [edited.report_id(link.link_id) for link in edited.links]
            region = affected_region(
                edited.links, link_report_ids, pieces, changed, float(max(distances))
            )
        stage("engine")
        log.info(
            "[3/4] raios %s, %s (%d retas, %s origens)…",
            ", ".join(keys),
            "só a região afetada" if region else "cidade inteira",
            len(pieces),
            region.live_count if region else len(pieces),
        )
        t_engine = time.perf_counter()
        run = self._analyzer.analyze(pieces, distances, live=region.live if region else None)
        engine_s = time.perf_counter() - t_engine
        log.info("[3/4] %s %s: ok em %.1fs", run.engine, run.engine_version, engine_s)

        scenario = raw_link_measures(report_ids, pieces, report_of_piece, run, cfg, radii=selected)
        if region is not None:
            _keep_base_outside(scenario, report_ids, region.output, base)

        stage("comparing")
        log.info("[4/4] comparação com a base (cortes de classe da base)")
        rows, summary = _compare(
            base,
            base_ids=base_ids,
            report_ids=report_ids,
            removed=edited.removed,
            closed=edited.closed,
            scenario=scenario,
            cfg=cfg,
        )

        new_links = [
            (link.link_id, link.coords) for link in edited.links if link.link_id in edited.added
        ]
        manifest = {
            "name": name,
            "base_analysis_id": base.analysis_id,
            "methodology_version": cfg.methodology_version,
            "preliminary": cfg.preliminary,
            "engine": run.engine,
            "engine_version": run.engine_version,
            "removed": edited.removed,
            "closed": edited.closed,
            "added": edited.added,
            "snaps_m": edited.snaps_m,
            "pieces": len(pieces),
            "radii": list(keys),
            "scope": "regiao" if region else "cidade",
            "region_links": len(region.output) if region else None,
            "region_live_pieces": region.live_count if region else None,
            "engine_seconds": round(engine_s, 1),
            "created_at": self._clock.now().isoformat(),
            "summary_result_zone": summary,
        }
        result = ScenarioResult(
            name=name,
            base_analysis_id=base.analysis_id,
            snapshot_id=base.snapshot_id,
            edits=[_edit_json(e) for e in edits],
            rows=list(rows.items()),
            new_links=new_links,
            manifest=manifest,
        )
        stage("saving")
        location = self._repository.save(result)
        log.info(
            "cenário %s concluído em %.1fs → %s", name, time.perf_counter() - started, location
        )
        return result, location


def _keep_base_outside(
    scenario: dict[str, FloatArray],
    report_ids: Sequence[str],
    output: frozenset[str],
    base: BaseAnalysis,
) -> None:
    """Fora da região afetada nada muda: o trecho fica com o valor publicado (exato)."""
    base_index = {link.link_id: i for i, link in enumerate(base.links)}
    for key, values in scenario.items():
        base_values = np.asarray(base.values[key], dtype=np.float64)
        for i, rid in enumerate(report_ids):
            j = base_index.get(rid)
            if rid not in output and j is not None:
                values[i] = base_values[j]


def _compare(
    base: BaseAnalysis,
    *,
    base_ids: list[str],
    report_ids: list[str],
    removed: list[str],
    closed: list[str],
    scenario: dict[str, FloatArray],
    cfg: AnalysisConfig,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, float]]]:
    """Valores, classes pelos cortes da base e delta de classe por trecho."""
    base_index = {lid: i for i, lid in enumerate(base_ids)}
    base_len = np.array([link.length_m for link in base.links])
    base_in_result = np.array([link.in_result_zone for link in base.links])
    rows: dict[str, dict[str, Any]] = {rid: {} for rid in report_ids}
    for rid in removed:
        rows[rid] = {"removed": True, "closed": True} if rid in closed else {"removed": True}
    summary: dict[str, dict[str, float]] = {}

    for key, scen_values in scenario.items():
        base_values = np.asarray(base.values[key], dtype=np.float64)
        cutoffs = class_cutoffs(
            np.where(base_in_result, base_values, np.nan), base_len, cfg.classes
        )
        scen_class = classify_by_cutoffs(scen_values, cutoffs)
        base_class = classify_by_cutoffs(base_values, cutoffs)
        up_km = down_km = 0.0
        for i, rid in enumerate(report_ids):
            row = rows[rid]
            row[key] = None if np.isnan(scen_values[i]) else round(float(scen_values[i]), 5)
            row[f"c_{key}"] = None if np.isnan(scen_class[i]) else int(scen_class[i])
            j = base_index.get(rid)
            if j is None:  # rua nova
                row["new"] = True
                continue
            if np.isnan(scen_class[i]) or np.isnan(base_class[j]):
                continue
            delta = int(scen_class[i] - base_class[j])
            row[f"d_{key}"] = delta
            if base_in_result[j] and delta > 0:
                up_km += base_len[j] / 1000
            elif base_in_result[j] and delta < 0:
                down_km += base_len[j] / 1000
        if key in SUMMARY_KEYS:
            summary[key] = {"km_up": round(up_km, 2), "km_down": round(down_km, 2)}
    return rows, summary


def _edit_json(edit: Edit) -> dict[str, Any]:
    if isinstance(edit, RemoveLink):
        return {"type": "close" if edit.closed else "remove", "link_id": edit.link_id}
    assert isinstance(edit, AddStreet)
    return {"type": "add", "coords": [list(c) for c in edit.coords]}
