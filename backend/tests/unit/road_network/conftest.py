from __future__ import annotations

from pathlib import Path

import pytest

from quantumco.road_network.domain.highway_filter import HighwayFilter
from quantumco.road_network.domain.osm import OsmWay
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

METHODOLOGY_V1 = Path(__file__).resolve().parents[3] / "methodology" / "v1"


@pytest.fixture
def methodology() -> YamlMethodology:
    return YamlMethodology(METHODOLOGY_V1)


@pytest.fixture
def highway_filter(methodology: YamlMethodology) -> HighwayFilter:
    return methodology.highway_filter()


def way(osm_id: int, nodes: list[tuple[int, float, float]], **tags: str) -> OsmWay:
    """Cria uma via a partir de (node_id, x, y)."""
    return OsmWay(
        osm_id=osm_id,
        node_ids=tuple(n for n, _, _ in nodes),
        coords=tuple((x, y) for _, x, y in nodes),
        tags={"highway": "residential", **tags},
    )
