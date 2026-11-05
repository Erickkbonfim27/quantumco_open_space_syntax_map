from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from quantumco.syntax_analysis.domain.segmentation import Link, Piece

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    snapshot_id: str
    snapshot_name: str
    links: tuple[Link, ...]


@dataclass(frozen=True, slots=True)
class RawMeasures:
    """Valores brutos por reta, no padrão do depthmapX (NC inclui a origem; 90° = 1)."""

    node_count: FloatArray
    total_depth: FloatArray
    choice: FloatArray


@dataclass(frozen=True, slots=True)
class EngineRun:
    engine: str
    engine_version: str
    by_distance: Mapping[int, RawMeasures]
    graph_nodes: int  # nós do grafo dual que o motor montou (teste de invariância)
    unmatched_pieces: int  # retas que o motor fundiu/descartou e voltaram sem valor


class NetworkSnapshotSource(Protocol):
    def latest(self) -> AnalysisInput | None: ...


class AngularAnalyzer(Protocol):
    def analyze(self, pieces: Sequence[Piece], distances_m: Sequence[int]) -> EngineRun: ...


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    snapshot_id: str
    snapshot_name: str
    link_ids: tuple[str, ...]
    columns: Mapping[str, FloatArray]  # nain_800, nach_n, c_nain_800 (classe 0..6) …
    manifest: Mapping[str, Any]


class AnalysisRepository(Protocol):
    def save(self, result: AnalysisResult) -> str: ...
