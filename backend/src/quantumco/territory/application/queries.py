"""Consulta: perfil territorial de um polígono desenhado pelo usuário."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from quantumco.territory.application.ports import Ring, TerritoryReader
from quantumco.territory.domain import profile
from quantumco.territory.domain.addresses import AddressHit, AddressQuery, rank
from quantumco.territory.domain.grid import CELL_AREA_M2

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

# Camadas que o mapa público pode ligar (cidade inteira).
MAP_LAYERS = ("risco", "suscet_inundacao", "saude", "escolas", "lugares")
PLACES_LAYER = "lugares"  # Overture places (comércio e serviços com nome)


def _places(counts: Mapping[str, int]) -> dict[str, Any]:
    """Lugares do Overture no polígono, por grupo."""
    return {
        "total": sum(counts.values()),
        "by_kind": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }


BUILDING_MIN_ZOOM = 13  # abaixo disso os prédios viram poeira: o tile sai vazio
MAX_ZOOM = 22
_LAYER_NAME = re.compile(r"[a-z0-9_]{1,40}")


class UnknownLayerError(LookupError):
    pass


class InvalidTileError(ValueError):
    pass


class GetPolygonProfile:
    def __init__(self, reader: TerritoryReader) -> None:
        self._reader = reader

    def layers(self) -> Sequence[Mapping[str, Any]]:
        return self._reader.layers()

    def map_layer(self, name: str) -> bytes | None:
        if name not in MAP_LAYERS:
            raise UnknownLayerError(f"camada desconhecida: {name} (há: {', '.join(MAP_LAYERS)})")
        return self._reader.map_layer(name)

    def images(self) -> Sequence[Mapping[str, Any]]:
        return self._reader.images()

    def image(self, layer: str) -> bytes | None:
        if not _LAYER_NAME.fullmatch(layer):
            raise UnknownLayerError(f"camada desconhecida: {layer}")
        return self._reader.image(layer)

    def building_tile(self, z: int, x: int, y: int) -> bytes:
        if not 0 <= z <= MAX_ZOOM or not (0 <= x < 2**z and 0 <= y < 2**z):
            raise InvalidTileError(f"tile inválido: {z}/{x}/{y}")
        if z < BUILDING_MIN_ZOOM:
            return b""
        return self._reader.building_tile(z, x, y)

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
            "demography": profile.demography(found.tracts),
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
            "places": (
                _places(counts.get(PLACES_LAYER, {})) if PLACES_LAYER in found.imported else None
            ),
            "buildings": profile.buildings(found.buildings, found.area_m2),
            "grid": profile.grid(found.grid, found.area_m2, CELL_AREA_M2),
            "features": {
                "points": [list(p) for p in found.points],
                "zones": [dict(z) for z in found.zone_shapes],
                "buildings": [list(b) for b in found.building_points],
            },
        }


class AddressIndex(Protocol):
    def candidates(self, words: Sequence[str], limit: int = 600) -> list[AddressHit]: ...


class SearchAddresses:
    """Endereços de Brusque (CNEFE 2022) que combinam com o texto digitado."""

    def __init__(self, index: AddressIndex) -> None:
        self._index = index

    def __call__(self, text: str, limit: int = 8) -> list[AddressHit]:
        query = AddressQuery.parse(text[:120])
        if not query.searchable:
            return []
        return rank(self._index.candidates(query.words), query, limit)
