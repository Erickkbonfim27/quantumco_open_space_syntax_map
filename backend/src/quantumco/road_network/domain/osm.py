from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from shapely.geometry import LineString, Polygon


class Zone(StrEnum):
    """Onde um elemento está em relação ao município."""

    RESULT = "result"  # dentro de Brusque: entra nos resultados
    BUFFER = "buffer"  # faixa externa: só reduz efeito de borda


@dataclass(frozen=True, slots=True)
class OsmWay:
    """Way do OSM já projetado no CRS da área de estudo.

    `node_ids[i]` corresponde a `coords[i]`. A conexão entre vias é dada pelos IDs de nó,
    nunca por cruzamento geométrico: pontes e túneis não conectam sem nó compartilhado.
    """

    osm_id: int
    node_ids: tuple[int, ...]
    coords: tuple[tuple[float, float], ...]
    tags: Mapping[str, str]

    def __post_init__(self) -> None:
        if len(self.node_ids) != len(self.coords):
            raise ValueError(f"way {self.osm_id}: node_ids e coords com tamanhos diferentes")
        if len(self.node_ids) < 2:
            raise ValueError(f"way {self.osm_id}: precisa de pelo menos 2 nós")

    @property
    def highway(self) -> str | None:
        return self.tags.get("highway")

    def line(self) -> LineString:
        return LineString(self.coords)

    def zone_within(self, municipality: Polygon) -> Zone:
        """Classifica pelo ponto médio ao longo da via."""
        midpoint = self.line().interpolate(0.5, normalized=True)
        return Zone.RESULT if municipality.covers(midpoint) else Zone.BUFFER


@dataclass(frozen=True, slots=True)
class OsmExtract:
    """Recorte datado do OSM: as vias e o limite municipal, já projetados."""

    ways: tuple[OsmWay, ...]
    municipality: Polygon
    osm_base_timestamp: datetime
    source: str
