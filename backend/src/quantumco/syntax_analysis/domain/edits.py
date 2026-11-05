"""Edições de cenário ("e se…") sobre a rede de uma análise base (Q23, Q52).

Regras:
- remover um trecho exige que ele exista;
- uma rua nova se conecta à rede pelas PONTAS: cada ponta é encaixada no ponto mais próximo de
  um trecho existente (até `snap_tolerance_m`); se cair no meio de um trecho, ele é dividido ali
  para virar um cruzamento de verdade. Cruzamentos no meio da rua nova NÃO conectam (como uma
  ponte) — para conectar, desenhe a rua em partes;
- metades de um trecho dividido continuam reportando o id original, para comparar com a base.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from shapely import STRtree
from shapely.geometry import LineString, Point
from shapely.ops import substring

from quantumco.syntax_analysis.domain.segmentation import Coords, Link

_ENDPOINT_EPS_M = 1.0  # encaixe a menos disso de uma ponta existente usa a própria ponta


class InvalidEditError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RemoveLink:
    link_id: str


@dataclass(frozen=True, slots=True)
class AddStreet:
    coords: Coords  # no CRS da análise (EPSG:31982)

    def __post_init__(self) -> None:
        if len(self.coords) < 2:
            raise InvalidEditError("rua nova precisa de pelo menos 2 pontos")


Edit = RemoveLink | AddStreet


@dataclass(slots=True)
class EditedNetwork:
    links: list[Link]
    # id do trecho no cenário → id do trecho na base (metades de trechos divididos)
    origin: dict[str, str] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    snaps_m: list[float] = field(default_factory=list)

    def report_id(self, link_id: str) -> str:
        return self.origin.get(link_id, link_id)


def apply_edits(
    links: Sequence[Link], edits: Sequence[Edit], snap_tolerance_m: float = 30.0
) -> EditedNetwork:
    by_id = {link.link_id: link for link in links}
    result = EditedNetwork(links=list(links))

    for edit in edits:
        if isinstance(edit, RemoveLink):
            if edit.link_id not in by_id:
                raise InvalidEditError(f"trecho {edit.link_id!r} não existe na rede base")
            result.links = [link for link in result.links if link.link_id != edit.link_id]
            result.removed.append(edit.link_id)

    for k, edit in enumerate(e for e in edits if isinstance(e, AddStreet)):
        coords = list(edit.coords)
        for end in (0, -1):
            snapped, distance = _snap(result, coords[end], snap_tolerance_m)
            coords[end] = snapped
            result.snaps_m.append(round(distance, 2))
        new_id = f"novo:{k}"
        result.links.append(Link(link_id=new_id, coords=tuple(coords), in_result_zone=True))
        result.added.append(new_id)
    return result


def _snap(
    network: EditedNetwork, point: tuple[float, float], tolerance_m: float
) -> tuple[tuple[float, float], float]:
    lines = [LineString(link.coords) for link in network.links]
    tree = STRtree(lines)
    target = Point(point)
    index = int(tree.nearest(target))
    line, link = lines[index], network.links[index]
    distance = float(line.distance(target))
    if distance > tolerance_m:
        raise InvalidEditError(
            f"ponta ({point[0]:.1f}, {point[1]:.1f}) está a {distance:.0f} m da rua mais próxima "
            f"(máximo {tolerance_m:.0f} m)"
        )
    along = float(line.project(target))
    if along <= _ENDPOINT_EPS_M:
        return link.coords[0], distance
    if along >= line.length - _ENDPOINT_EPS_M:
        return link.coords[-1], distance

    # divide o trecho no ponto de encaixe para virar cruzamento
    first, second = substring(line, 0, along), substring(line, along, line.length)
    snapped = tuple(np.asarray(first.coords[-1], dtype=float).tolist())
    base_id = network.report_id(link.link_id)
    halves = [
        Link(f"{link.link_id}/a", tuple(map(tuple, first.coords)), link.in_result_zone),  # type: ignore[arg-type]
        Link(f"{link.link_id}/b", tuple(map(tuple, second.coords)), link.in_result_zone),  # type: ignore[arg-type]
    ]
    network.links[index : index + 1] = halves
    for half in halves:
        network.origin[half.link_id] = base_id
    return (float(snapped[0]), float(snapped[1])), distance
