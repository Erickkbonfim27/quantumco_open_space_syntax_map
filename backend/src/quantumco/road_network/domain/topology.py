"""Montagem da topologia: vias do OSM → trechos entre cruzamentos (links).

Regras (methodology/v1/cleaning.yaml):
- conexão só por nó OSM compartilhado (pontes e túneis não conectam sem nó comum);
- cada via é cortada nos nós que pertencem a mais de uma via aceita, ou que se repetem
  na mesma via (laços); os nós de grau 2 desaparecem por construção;
- só o maior componente conectado é analisável (Q44).
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx
from shapely.geometry import LineString

from quantumco.road_network.domain.osm import OsmWay, Zone


@dataclass(frozen=True, slots=True)
class RoadLink:
    """Trecho de rua entre dois cruzamentos (ou ponta solta)."""

    link_id: str
    osm_way_id: int
    from_node: int
    to_node: int
    coords: tuple[tuple[float, float], ...]
    highway: str
    zone: Zone
    is_bridge: bool
    is_tunnel: bool

    @property
    def length_m(self) -> float:
        return float(LineString(self.coords).length)


@dataclass(frozen=True, slots=True)
class AcceptedWay:
    way: OsmWay
    zone: Zone


def split_into_links(ways: Iterable[AcceptedWay]) -> list[RoadLink]:
    accepted = list(ways)
    usage: Counter[int] = Counter()
    for item in accepted:
        node_ids = item.way.node_ids
        usage.update(set(node_ids))
        # nó repetido dentro da mesma via (laço) também é ponto de corte
        repeated = [n for n, c in Counter(node_ids).items() if c > 1]
        usage.update(repeated)

    links: list[RoadLink] = []
    for item in accepted:
        way = item.way
        tags = way.tags
        last = len(way.node_ids) - 1
        cut_points = [0] + [i for i in range(1, last) if usage[way.node_ids[i]] > 1] + [last]
        for k, (start, end) in enumerate(itertools.pairwise(cut_points)):
            links.append(
                RoadLink(
                    link_id=f"{way.osm_id}:{k}",
                    osm_way_id=way.osm_id,
                    from_node=way.node_ids[start],
                    to_node=way.node_ids[end],
                    coords=way.coords[start : end + 1],
                    highway=way.highway or "",
                    zone=item.zone,
                    is_bridge=tags.get("bridge", "no") not in ("no", ""),
                    is_tunnel=tags.get("tunnel", "no") not in ("no", ""),
                )
            )
    return links


@dataclass(frozen=True, slots=True)
class ComponentSplit:
    kept: tuple[RoadLink, ...]
    excluded: tuple[RoadLink, ...]
    component_count: int


def keep_largest_component(links: Iterable[RoadLink]) -> ComponentSplit:
    """Separa o maior componente conectado (por extensão total) do resto."""
    all_links = list(links)
    if not all_links:
        return ComponentSplit(kept=(), excluded=(), component_count=0)

    graph: nx.MultiGraph[int] = nx.MultiGraph()
    for index, link in enumerate(all_links):
        graph.add_edge(link.from_node, link.to_node, key=index)

    components = list(nx.connected_components(graph))

    def extent(nodes: set[int]) -> float:
        return sum(all_links[key].length_m for _, _, key in graph.subgraph(nodes).edges(keys=True))

    largest = max(components, key=extent)
    kept = tuple(link for link in all_links if link.from_node in largest)
    excluded = tuple(link for link in all_links if link.from_node not in largest)
    return ComponentSplit(kept=kept, excluded=excluded, component_count=len(components))
