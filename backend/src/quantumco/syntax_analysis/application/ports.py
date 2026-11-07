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
    ibge_code: str
    crs_epsg: int  # CRS métrico do snapshot (as coordenadas dos trechos estão nele)


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
    def latest(self, ibge_code: str) -> AnalysisInput | None:
        """O snapshot publicado da cidade."""
        ...


class AngularAnalyzer(Protocol):
    def analyze(
        self,
        pieces: Sequence[Piece],
        distances_m: Sequence[int],
        live: Sequence[bool] | None = None,
        crs_epsg: int | None = None,
    ) -> EngineRun:
        """`live`: retas que são origem (None = todas); as outras entram só como caminho.
        `crs_epsg`: CRS métrico das retas (None = o padrão do motor)."""
        ...


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    snapshot_id: str
    snapshot_name: str
    link_ids: tuple[str, ...]
    columns: Mapping[str, FloatArray]  # nain_800, nach_n, c_nain_800 (classe 0..6) …
    manifest: Mapping[str, Any]
    ibge_code: str


class AnalysisRepository(Protocol):
    def save(self, result: AnalysisResult) -> str: ...


@dataclass(frozen=True, slots=True)
class BaseAnalysis:
    """Análise publicada usada como referência de um cenário."""

    analysis_id: str
    snapshot_id: str
    links: tuple[Link, ...]
    values: Mapping[str, FloatArray]  # nain_n, nach_800, … alinhados a `links`
    ibge_code: str
    crs_epsg: int


class BaseAnalysisSource(Protocol):
    def current(self, ibge_code: str) -> BaseAnalysis | None:
        """A análise publicada da cidade."""
        ...


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    base_analysis_id: str
    snapshot_id: str
    ibge_code: str
    crs_epsg: int  # das coordenadas das ruas novas
    edits: Sequence[Mapping[str, Any]]
    rows: Sequence[tuple[str, Mapping[str, float | int | bool | None]]]  # (trecho, medidas)
    new_links: Sequence[tuple[str, Sequence[tuple[float, float]]]]
    manifest: Mapping[str, Any]


class ScenarioRepository(Protocol):
    def save(self, result: ScenarioResult) -> str: ...

    def delete(self, name: str) -> None: ...
