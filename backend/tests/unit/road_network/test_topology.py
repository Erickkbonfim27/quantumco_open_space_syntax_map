from __future__ import annotations

import pytest

from quantumco.road_network.domain.osm import Zone
from quantumco.road_network.domain.topology import (
    AcceptedWay,
    keep_largest_component,
    split_into_links,
)

from .conftest import way


def accepted(*ways: object) -> list[AcceptedWay]:
    return [AcceptedWay(way=w, zone=Zone.RESULT) for w in ways]  # type: ignore[arg-type]


def test_way_is_split_only_at_shared_nodes() -> None:
    # A: 1-2-3-4 (horizontal), B: 10-3-11 (vertical cruzando em 3)
    a = way(1, [(1, 0, 0), (2, 10, 0), (3, 20, 0), (4, 30, 0)])
    b = way(2, [(10, 20, -10), (3, 20, 0), (11, 20, 10)])
    links = split_into_links(accepted(a, b))
    by_way = {(link.osm_way_id, link.from_node, link.to_node) for link in links}
    # nó 2 é de grau 2 e some; A vira 1→3 e 3→4
    assert by_way == {(1, 1, 3), (1, 3, 4), (2, 10, 3), (2, 3, 11)}


def test_bridge_crossing_without_shared_node_does_not_connect() -> None:
    street = way(1, [(1, 0, 0), (2, 20, 0)])
    bridge = way(2, [(10, 10, -10), (11, 10, 10)], bridge="yes", layer="1")
    links = split_into_links(accepted(street, bridge))
    assert len(links) == 2
    split = keep_largest_component(links)
    assert split.component_count == 2
    assert next(link for link in links if link.osm_way_id == 2).is_bridge


def test_loop_way_is_cut_at_repeated_node() -> None:
    # rotatória fechada: 1-2-3-1, com acesso em 1
    loop = way(1, [(1, 0, 0), (2, 10, 0), (3, 5, 8), (1, 0, 0)], junction="roundabout")
    access = way(2, [(9, -10, 0), (1, 0, 0)])
    links = split_into_links(accepted(loop, access))
    loop_links = [link for link in links if link.osm_way_id == 1]
    assert len(loop_links) == 1
    assert loop_links[0].from_node == loop_links[0].to_node == 1


def test_largest_component_by_length_and_lengths_add_up() -> None:
    main = way(1, [(1, 0, 0), (2, 1000, 0)])
    branch = way(2, [(2, 1000, 0), (3, 1000, 500)])
    island = way(3, [(7, 5000, 5000), (8, 5050, 5000)])
    links = split_into_links(accepted(main, branch, island))
    split = keep_largest_component(links)
    assert {link.osm_way_id for link in split.kept} == {1, 2}
    assert [link.osm_way_id for link in split.excluded] == [3]
    total = sum(link.length_m for link in links)
    kept = sum(link.length_m for link in split.kept)
    excluded = sum(link.length_m for link in split.excluded)
    assert kept + excluded == pytest.approx(total)


def test_empty_input() -> None:
    split = keep_largest_component([])
    assert split.kept == ()
    assert split.excluded == ()
    assert split.component_count == 0
