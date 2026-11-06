"""A análise oficial e o cenário precisam calcular a medida de cada trecho do mesmo jeito.

O cenário é comparado, trecho a trecho, com a análise publicada. Se as duas contas divergissem,
um cenário apareceria "mudando" ruas que a edição nem tocou.

O motor aqui é falso e local: o valor de cada reta depende só da geometria dela. Assim, tirar um
trecho da rede não muda o valor dos outros, e qualquer diferença só pode vir da agregação.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pytest

from quantumco.syntax_analysis.application.config import AnalysisConfig
from quantumco.syntax_analysis.application.ports import (
    AnalysisInput,
    AnalysisResult,
    BaseAnalysis,
    EngineRun,
    RawMeasures,
    ScenarioResult,
)
from quantumco.syntax_analysis.application.run_analysis import RunAnalysis
from quantumco.syntax_analysis.application.run_scenario import RunScenario
from quantumco.syntax_analysis.domain.edits import RemoveLink
from quantumco.syntax_analysis.domain.measures import nain
from quantumco.syntax_analysis.domain.radius import Radius
from quantumco.syntax_analysis.domain.segmentation import Link, Piece

from ...support import FixedClock

# Trechos com mais de uma reta (para a média ponderada pesar) e um fora da zona de resultado.
LINKS = (
    Link("a", ((0.0, 0.0), (100.0, 0.0), (100.0, 60.0)), True),
    Link("b", ((100.0, 60.0), (200.0, 60.0), (260.0, 120.0)), True),
    Link("c", ((0.0, 0.0), (0.0, 80.0), (-40.0, 140.0)), True),
    Link("d", ((200.0, 60.0), (200.0, 200.0)), True),
    Link("e", ((260.0, 120.0), (300.0, 200.0), (380.0, 200.0)), False),
    Link("f", ((500.0, 500.0), (520.0, 500.0)), True),
)
# Retas isoladas no raio (profundidade total 0): valor indefinido. "e#1" deixa o trecho "e" com
# valor só numa reta; "f#0" deixa o trecho "f" inteiro sem valor.
UNDEFINED = {"e#1", "f#0"}

CONFIG = AnalysisConfig(
    methodology_version="teste",
    radii=(Radius(400), Radius(None)),
    radius_n_m=2000,
    simplification_m=2.0,
    classes=7,
    preliminary=True,
)


def fake_values(piece: Piece, distance_m: int) -> tuple[float, float, float]:
    """(NC, TD, escolha) de uma reta: só geometria e raio."""
    length = piece.length_m
    td = 0.0 if piece.piece_id in UNDEFINED else 5 + length / 20
    return 10 + length / 10 + distance_m / 500, td, length * (1 + distance_m / 1000)


class LocalEngine:
    def analyze(self, pieces: Sequence[Piece], distances_m: Sequence[int]) -> EngineRun:
        by_distance: dict[int, RawMeasures] = {}
        for distance in distances_m:
            rows = np.array([fake_values(p, distance) for p in pieces])
            by_distance[distance] = RawMeasures(
                node_count=rows[:, 0], total_depth=rows[:, 1], choice=rows[:, 2]
            )
        return EngineRun("falso", "0", by_distance, graph_nodes=len(pieces), unmatched_pieces=0)


class Network:
    def latest(self) -> AnalysisInput:
        return AnalysisInput("snapshot-1", "snapshot-1", LINKS)


class Analyses:
    def __init__(self) -> None:
        self.saved: AnalysisResult | None = None

    def save(self, result: AnalysisResult) -> str:
        self.saved = result
        return "memória"


class Base:
    def __init__(self, base: BaseAnalysis) -> None:
        self._base = base

    def current(self) -> BaseAnalysis:
        return self._base


class Scenarios:
    def __init__(self) -> None:
        self.saved: ScenarioResult | None = None

    def save(self, result: ScenarioResult) -> str:
        self.saved = result
        return "memória"

    def delete(self, name: str) -> None:
        raise NotImplementedError


def published_analysis() -> AnalysisResult:
    analyses = Analyses()
    RunAnalysis(Network(), LocalEngine(), analyses, CONFIG, FixedClock())()
    assert analyses.saved is not None
    return analyses.saved


def test_scenario_matches_the_published_analysis_on_untouched_links() -> None:
    official = published_analysis()
    measures = {k: v for k, v in official.columns.items() if k.startswith(("nain_", "nach_"))}
    # o teste só vale se há trecho com e sem valor, senão não exercita o caso indefinido
    assert np.isnan(measures["nain_400"]).any()
    assert (~np.isnan(measures["nain_400"])).any()

    scenarios = Scenarios()
    base = BaseAnalysis("base-1", "snapshot-1", LINKS, measures)
    RunScenario(
        base=Base(base),
        analyzer=LocalEngine(),
        repository=scenarios,
        config=CONFIG,
        clock=FixedClock(),
    )("sem-o-trecho-d", [RemoveLink("d")])

    assert scenarios.saved is not None
    rows: Mapping[str, Mapping[str, Any]] = dict(scenarios.saved.rows)
    assert rows["d"]["removed"] is True
    for index, link in enumerate(LINKS):
        if link.link_id == "d":
            continue
        for key, column in measures.items():
            expected = None if np.isnan(column[index]) else round(float(column[index]), 5)
            assert rows[link.link_id][key] == expected, f"trecho {link.link_id}, {key}"


def test_link_value_is_the_length_weighted_mean_of_its_pieces() -> None:
    """Âncora independente: a conta escrita à mão, sem passar pelo código compartilhado."""
    official = published_analysis()
    # trecho "a": duas retas, de 100 m e 60 m (nenhuma indefinida)
    pieces = (
        Piece("a#0", "a", (0.0, 0.0), (100.0, 0.0)),
        Piece("a#1", "a", (100.0, 0.0), (100.0, 60.0)),
    )
    values = []
    for piece in pieces:
        nc, td, _ = fake_values(piece, 400)
        values.append(float(nain(np.array([nc]), np.array([td]))[0]))
    expected = (values[0] * 100 + values[1] * 60) / 160

    index = [link.link_id for link in LINKS].index("a")
    assert official.columns["nain_400"][index] == pytest.approx(expected)

    # trecho "e": só a reta "e#0" tem valor; a indefinida não entra na média
    e0 = Piece("e#0", "e", (260.0, 120.0), (300.0, 200.0))
    nc, td, _ = fake_values(e0, 400)
    index_e = [link.link_id for link in LINKS].index("e")
    assert official.columns["nain_400"][index_e] == pytest.approx(
        float(nain(np.array([nc]), np.array([td]))[0])
    )
    # trecho "f": todas as retas indefinidas, trecho sem valor
    index_f = [link.link_id for link in LINKS].index("f")
    assert np.isnan(official.columns["nain_400"][index_f])
