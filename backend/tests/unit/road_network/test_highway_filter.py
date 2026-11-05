from __future__ import annotations

import pytest

from quantumco.road_network.domain.highway_filter import FilterVariant, HighwayFilter
from quantumco.road_network.domain.osm import Zone


@pytest.mark.parametrize(
    ("tags", "zone", "accepted", "reason"),
    [
        ({"highway": "residential"}, Zone.RESULT, True, "included"),
        ({"highway": "primary_link"}, Zone.RESULT, True, "included_link"),
        ({"highway": "steps"}, Zone.RESULT, True, "included"),
        ({"highway": "service"}, Zone.RESULT, True, "included"),
        ({"highway": "service", "service": "driveway"}, Zone.RESULT, False, "private_service"),
        ({"highway": "service", "service": "parking_aisle"}, Zone.BUFFER, False, "private_service"),
        ({"highway": "residential", "access": "private"}, Zone.RESULT, False, "access_excluded"),
        ({"highway": "track"}, Zone.BUFFER, True, "included_buffer_only"),
        ({"highway": "track"}, Zone.RESULT, False, "buffer_only_class_in_result_zone"),
        ({"highway": "footway"}, Zone.RESULT, False, "pedestrian_variant_only"),
        ({"highway": "pedestrian", "area": "yes"}, Zone.RESULT, False, "area"),
        ({"highway": "proposed"}, Zone.RESULT, False, "class_not_included:proposed"),
        (
            {"highway": "residential_link"},
            Zone.RESULT,
            False,
            "class_not_included:residential_link",
        ),
    ],
)
def test_base_filter(
    highway_filter: HighwayFilter,
    tags: dict[str, str],
    zone: Zone,
    accepted: bool,
    reason: str,
) -> None:
    decision = highway_filter.decide(tags, zone)
    assert (decision.accepted, decision.reason) == (accepted, reason)


def test_pedestrian_variant_includes_footways(highway_filter: HighwayFilter) -> None:
    decision = highway_filter.decide(
        {"highway": "footway"}, Zone.RESULT, FilterVariant.WITH_PEDESTRIAN
    )
    assert decision.accepted
