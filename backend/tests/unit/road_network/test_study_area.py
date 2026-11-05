from __future__ import annotations

import pytest

from quantumco.road_network.domain.study_area import InvalidStudyAreaError, StudyArea
from quantumco.road_network.infrastructure.yaml_methodology import YamlMethodology


def test_methodology_v1_selects_brusque_sc_by_code(methodology: YamlMethodology) -> None:
    area = methodology.study_area()
    assert area == StudyArea(
        ibge_code="4202909", osm_relation_id=296588, buffer_m=7000.0, crs_epsg=31982
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ibge_code": "Brusque"},
        {"ibge_code": "42029"},
        {"osm_relation_id": 0},
        {"buffer_m": -1.0},
    ],
)
def test_invalid_study_area(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {
        "ibge_code": "4202909",
        "osm_relation_id": 296588,
        "buffer_m": 7000.0,
        "crs_epsg": 31982,
    }
    with pytest.raises(InvalidStudyAreaError):
        StudyArea(**{**base, **kwargs})  # type: ignore[arg-type]
