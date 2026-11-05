from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from quantumco.road_network.domain.osm import Zone


class FilterVariant(StrEnum):
    BASE = "base"
    WITH_PEDESTRIAN = "with_pedestrian"  # variante de sensibilidade (Q13)


@dataclass(frozen=True, slots=True)
class FilterDecision:
    accepted: bool
    reason: str


@dataclass(frozen=True, slots=True)
class HighwayFilter:
    """Regra de inclusão de vias (Q7, Q13). Cada rejeição tem um motivo contável."""

    version: str
    included: frozenset[str]
    link_variants_of: frozenset[str]
    buffer_only: frozenset[str]
    pedestrian_variant: frozenset[str]
    excluded_service: frozenset[str]
    excluded_access: frozenset[str]

    def decide(
        self,
        tags: Mapping[str, str],
        zone: Zone,
        variant: FilterVariant = FilterVariant.BASE,
    ) -> FilterDecision:
        highway = tags.get("highway")
        if highway is None:
            return FilterDecision(False, "no_highway_tag")
        if tags.get("area") == "yes":
            return FilterDecision(False, "area")
        if tags.get("access") in self.excluded_access:
            return FilterDecision(False, "access_excluded")
        if highway == "service" and tags.get("service") in self.excluded_service:
            return FilterDecision(False, "private_service")

        base_class = highway.removesuffix("_link")
        if highway.endswith("_link") and base_class in self.link_variants_of:
            return FilterDecision(True, "included_link")
        if highway in self.included:
            return FilterDecision(True, "included")
        if highway in self.buffer_only:
            if zone is Zone.BUFFER:
                return FilterDecision(True, "included_buffer_only")
            return FilterDecision(False, "buffer_only_class_in_result_zone")
        if highway in self.pedestrian_variant:
            if variant is FilterVariant.WITH_PEDESTRIAN:
                return FilterDecision(True, "included_pedestrian_variant")
            return FilterDecision(False, "pedestrian_variant_only")
        return FilterDecision(False, f"class_not_included:{highway}")
