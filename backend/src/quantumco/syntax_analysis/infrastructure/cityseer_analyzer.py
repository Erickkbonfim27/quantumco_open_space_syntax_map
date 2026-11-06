"""Adaptador `AngularAnalyzer` com o cityseer (motor de produção, Q43).

O grafo é montado direto das retas (sem a limpeza automática do cityseer, Q47). A conversão
para o padrão do depthmapX foi conferida em malhas mínimas:
- `cc_density` não conta a origem → NC = density + 1;
- `cc_farness` soma (1 + Δângulo/90) por destino → TD = farness − density (90° = 1);
- `cc_betweenness` conta cada par origem-destino uma vez.
A equivalência numérica com o depthmapX ainda precisa passar no CI (por isso "preliminar").
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from importlib.metadata import version

import geopandas as gpd
import numpy as np
from cityseer.metrics import networks
from cityseer.tools import graphs, io
from shapely.geometry import LineString

from quantumco.syntax_analysis.application.ports import EngineRun, RawMeasures
from quantumco.syntax_analysis.domain.segmentation import Piece

log = logging.getLogger(__name__)


class CityseerAnalyzer:
    def __init__(self, crs_epsg: int = 31982) -> None:
        self._crs = crs_epsg

    def analyze(
        self,
        pieces: Sequence[Piece],
        distances_m: Sequence[int],
        live: Sequence[bool] | None = None,
    ) -> EngineRun:
        """`live[i]` False: a reta i entra só como caminho (não é origem e sai sem valor)."""
        frame = gpd.GeoDataFrame(
            {"piece_id": [p.piece_id for p in pieces]},
            geometry=[LineString([p.start, p.end]) for p in pieces],
            crs=self._crs,
        )
        graph = io.nx_from_generic_geopandas(frame, drop_self_loops_dist=0)
        dual = graphs.nx_to_dual(graph)

        # nó do dual → reta de origem (o id do nó dual é "<nóA>_<nóB>_k<chave>")
        node_to_piece: dict[str, str] = {}
        for u, v, k, data in graph.edges(keys=True, data=True):
            node_to_piece[f"{u}_{v}_k{k}"] = data["piece_id"]
            node_to_piece[f"{v}_{u}_k{k}"] = data["piece_id"]
        position = {p.piece_id: i for i, p in enumerate(pieces)}
        if live is not None:
            for node in dual.nodes:
                i = position.get(node_to_piece.get(str(node), ""), -1)
                dual.nodes[node]["live"] = bool(live[i]) if i >= 0 else False
            log.info("origens no motor: %d de %d retas", sum(live), len(pieces))

        nodes, _, structure = io.network_structure_from_nx(dual)
        log.info("grafo dual: %d nós, %d arestas", dual.number_of_nodes(), dual.number_of_edges())

        nodes = networks.centrality_simplest(structure, nodes, distances=list(distances_m))
        rows = np.array([position.get(node_to_piece.get(str(idx), ""), -1) for idx in nodes.index])
        valid = rows >= 0

        by_distance: dict[int, RawMeasures] = {}
        for d in distances_m:
            density = nodes[f"cc_density_{d}_ang"].to_numpy(dtype=np.float64)
            farness = nodes[f"cc_farness_{d}_ang"].to_numpy(dtype=np.float64)
            betweenness = nodes[f"cc_betweenness_{d}_ang"].to_numpy(dtype=np.float64)
            nc, td, ch = (np.full(len(pieces), np.nan) for _ in range(3))
            nc[rows[valid]] = density[valid] + 1.0
            td[rows[valid]] = farness[valid] - density[valid]
            ch[rows[valid]] = betweenness[valid]
            by_distance[d] = RawMeasures(node_count=nc, total_depth=td, choice=ch)

        matched = len(set(rows[valid].tolist()))
        return EngineRun(
            engine="cityseer",
            engine_version=version("cityseer"),
            by_distance=by_distance,
            graph_nodes=dual.number_of_nodes(),
            unmatched_pieces=len(pieces) - matched,
        )
