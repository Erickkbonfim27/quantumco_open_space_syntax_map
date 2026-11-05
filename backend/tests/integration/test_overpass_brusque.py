"""Teste contra o Overpass real. Rodar com: uv run pytest -m network"""

from __future__ import annotations

from pathlib import Path

import pytest

from quantumco.road_network.infrastructure.overpass_source import OverpassWaySource
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology

METHODOLOGY_V1 = Path(__file__).resolve().parents[2] / "methodology" / "v1"


@pytest.mark.network
def test_fetch_brusque_sc() -> None:
    area = YamlMethodology(METHODOLOGY_V1).study_area()
    extract = OverpassWaySource().fetch(area)
    # Brusque-SC tem ~284 km²; a Brusque francesa tem poucos km² (Q14)
    assert 250e6 < extract.municipality.area < 320e6
    assert len(extract.ways) > 5000
