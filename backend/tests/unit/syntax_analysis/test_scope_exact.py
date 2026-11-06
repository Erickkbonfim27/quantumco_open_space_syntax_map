"""O recálculo só da região afetada é EXATO: mesmo resultado da cidade inteira, com o cityseer.

Malha quadriculada (com diagonais, para os ângulos variarem). Remove-se um trecho no meio e
compara-se, reta a reta:
- dentro da região de saída: recorte (origens só perto da edição) == cálculo completo;
- fora dela: cálculo completo com a edição == cálculo completo sem a edição (nada mudou).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.ports import AnalysisInput, BaseAnalysis, EngineRun
from quantumco.syntax_analysis.application.run_analysis import RunAnalysis
from quantumco.syntax_analysis.application.run_scenario import RunScenario
from quantumco.syntax_analysis.domain.edits import RemoveLink, apply_edits
from quantumco.syntax_analysis.domain.radius import Radius
from quantumco.syntax_analysis.domain.scope import affected_region
from quantumco.syntax_analysis.domain.segmentation import Link, explode
from quantumco.syntax_analysis.infrastructure.cityseer_analyzer import CityseerAnalyzer

from ...support import FixedClock

STEP = 100.0
SIZE = 16  # 16 × 16 cruzamentos: 1,5 km de lado
RADIUS = 200


def grid() -> list[Link]:
    links: list[Link] = []
    for i in range(SIZE):
        for j in range(SIZE):
            x, y = i * STEP, j * STEP
            if i + 1 < SIZE:
                links.append(Link(f"h{i}_{j}", ((x, y), (x + STEP, y)), True))
            if j + 1 < SIZE:
                links.append(Link(f"v{i}_{j}", ((x, y), (x, y + STEP)), True))
            if (i + j) % 5 == 0 and i + 1 < SIZE and j + 1 < SIZE:
                links.append(Link(f"d{i}_{j}", ((x, y), (x + STEP, y + STEP)), True))
    return links


class _Network:
    def latest(self) -> AnalysisInput:
        return AnalysisInput("s1", "s1", tuple(grid()))


class _Saved:
    def __init__(self) -> None:
        self.saved: Any = None

    def save(self, result: Any) -> str:
        self.saved = result
        return "memória"

    def delete(self, name: str) -> None:
        raise NotImplementedError


def test_scenario_use_case_with_local_scope_equals_whole_city_rows() -> None:
    """Ponta a ponta (motor real): valores, classes e deltas iguais nos raios locais."""
    cfg = AnalysisConfig("teste", (Radius(RADIUS), Radius(None)), 5000, 0.0, 7, True)
    analyses = _Saved()
    RunAnalysis(_Network(), CityseerAnalyzer(), analyses, cfg, FixedClock())()
    official = analyses.saved
    values = {k: v for k, v in official.columns.items() if k.startswith(("nain_", "nach_"))}
    base = BaseAnalysis("b1", "s1", tuple(grid()), values)

    class _Base:
        def current(self) -> BaseAnalysis:
            return base

    def run(radii: list[str] | None) -> dict[str, Any]:
        saved = _Saved()
        RunScenario(
            base=_Base(), analyzer=CityseerAnalyzer(), repository=saved, config=cfg,
            clock=FixedClock(),
        )("sem-h7-7", [RemoveLink("h7_7")], radii=radii)  # fmt: skip
        return {"rows": dict(saved.saved.rows), "manifest": saved.saved.manifest}

    whole, local = run(None), run([str(RADIUS)])
    assert local["manifest"]["scope"] == "regiao"
    assert whole["manifest"]["scope"] == "cidade"
    assert 0 < local["manifest"]["region_links"] < len(grid()) / 2
    keys = [f"{m}_{RADIUS}" for m in ("nain", "nach")]
    for link_id, row in whole["rows"].items():
        mine = local["rows"][link_id]
        for key in keys:
            for prefix in ("", "c_", "d_"):
                got, want = mine.get(prefix + key), row.get(prefix + key)
                if isinstance(want, float):
                    assert got == pytest.approx(want, rel=1e-6), (link_id, prefix + key)
                else:
                    assert got == want, (link_id, prefix + key)
        assert "nain_n" not in mine  # raio não pedido não aparece


def by_piece(run: EngineRun, ids: list[str]) -> dict[str, tuple[float, float, float]]:
    raw = run.by_distance[RADIUS]
    return {
        pid: (float(raw.node_count[k]), float(raw.total_depth[k]), float(raw.choice[k]))
        for k, pid in enumerate(ids)
    }


def test_local_recalculation_matches_the_whole_city() -> None:
    engine = CityseerAnalyzer()
    base_links = grid()
    base_pieces = explode(base_links, 0)
    base = by_piece(engine.analyze(base_pieces, [RADIUS]), [p.piece_id for p in base_pieces])

    removed = "h7_7"
    edited = apply_edits(base_links, [RemoveLink(removed)])
    pieces = explode(edited.links, 0)
    ids = [p.piece_id for p in pieces]
    full = by_piece(engine.analyze(pieces, [RADIUS]), ids)

    changed = [next(link.coords for link in base_links if link.link_id == removed)]
    report_ids = [edited.report_id(link.link_id) for link in edited.links]
    region = affected_region(edited.links, report_ids, pieces, changed, RADIUS)
    local = by_piece(engine.analyze(pieces, [RADIUS], live=region.live), ids)

    # a região precisa ser de fato menor que a cidade, senão o teste não prova nada
    assert 0 < len(region.output) < len(edited.links) / 2
    assert region.live_count < len(pieces)

    inside = [p for p in pieces if p.link_id in region.output]
    outside = [p for p in pieces if p.link_id not in region.output]
    assert inside
    assert outside
    for p in inside:
        assert local[p.piece_id] == pytest.approx(full[p.piece_id], rel=1e-9, abs=1e-9), p.piece_id
    for p in outside:
        assert full[p.piece_id] == pytest.approx(base[p.piece_id], rel=1e-9, abs=1e-9), p.piece_id
    # o motor respeitou as origens: retas fora delas não foram calculadas (senão o teste seria
    # trivial: um motor que ignorasse `live` calcularia tudo e passaria igual)
    not_live = [p.piece_id for p, on in zip(pieces, region.live, strict=True) if not on]
    assert not_live
    assert all(
        np.isnan(local[pid][1]) or local[pid] != pytest.approx(full[pid]) for pid in not_live
    )
    # e a edição mexeu de verdade em alguém dentro da região
    assert any(
        not np.allclose(full[p.piece_id], base[p.piece_id]) for p in inside if p.piece_id in base
    )
