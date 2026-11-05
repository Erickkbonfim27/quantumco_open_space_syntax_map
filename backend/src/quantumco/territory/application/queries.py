"""Consulta: perfil territorial de um polígono desenhado pelo usuário."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from quantumco.territory.application.ports import Ring, TerritoryReader
from quantumco.territory.domain import profile

# Espécies do CNEFE 2022 (COD_ESPECIE) que viram contagens no painel.
CNEFE_KINDS = (
    "domicilio",
    "domicilio_coletivo",
    "agropecuario",
    "ensino",
    "saude",
    "outras_finalidades",
    "em_construcao",
    "religioso",
)
NAMED_LIMIT = 12


class GetPolygonProfile:
    def __init__(self, reader: TerritoryReader) -> None:
        self._reader = reader

    def layers(self) -> Sequence[Mapping[str, Any]]:
        return self._reader.layers()

    def __call__(self, ring: Ring) -> dict[str, Any] | None:
        found = self._reader.overlaps(ring)
        if found is None:
            return None
        area_km2 = found.area_m2 / 1e6

        counts: dict[str, dict[str, int]] = defaultdict(dict)
        health_sus = 0
        for c in found.place_counts:
            counts[c.layer][c.kind] = counts[c.layer].get(c.kind, 0) + c.count
            if c.layer == "cnes":
                health_sus += c.flagged
        names: dict[str, list[str]] = defaultdict(list)
        for p in found.named_places:
            key = f"{p.layer}:{p.kind}"
            if len(names[key]) < NAMED_LIMIT:
                names[key].append(p.name)

        cnefe = {kind: counts.get("cnefe", {}).get(kind, 0) for kind in CNEFE_KINDS}
        addresses = sum(cnefe.values())
        health = counts.get("cnes", {})
        return {
            "population": profile.population(found.tracts, area_km2),
            "streetscape": profile.streetscape(found.tracts),
            "risk": profile.risk(found.zones),
            "susceptibility": profile.susceptibility(found.zones, found.area_m2),
            "addresses": {
                "total": addresses,
                "by_kind": cnefe,
                "non_residential_share": (
                    round(1 - (cnefe["domicilio"] + cnefe["domicilio_coletivo"]) / addresses, 4)
                    if addresses
                    else None
                ),
                "schools": names.get("cnefe:ensino", []),
            },
            "health": {
                "total": sum(health.values()),
                "sus": health_sus,
                "by_kind": dict(sorted(health.items(), key=lambda kv: -kv[1])),
                "public_units": names.get("cnes:atencao_basica", [])
                + names.get("cnes:hospital", [])
                + names.get("cnes:urgencia", []),
            },
            "features": {
                "points": [list(p) for p in found.points],
                "zones": [dict(z) for z in found.zone_shapes],
            },
        }
