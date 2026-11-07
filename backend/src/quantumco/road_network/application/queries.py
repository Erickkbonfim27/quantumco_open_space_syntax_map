"""Lado de leitura (CQRS leve, Q53): a rede publicada que a API entrega ao frontend."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PublishedNetwork:
    """Rede pronta para o navegador: GeoJSON em WGS84 já serializado + manifesto."""

    snapshot_id: str
    manifest: Mapping[str, Any]
    links_geojson: bytes
    municipality_geojson: bytes


class PublishedNetworkReader(Protocol):
    def current(self, ibge_code: str) -> PublishedNetwork | None:
        """O snapshot publicado da cidade, ou None se ela ainda não tem."""
        ...


class NoSnapshotError(LookupError):
    pass


class GetCurrentNetwork:
    def __init__(self, reader: PublishedNetworkReader) -> None:
        self._reader = reader

    def __call__(self, ibge_code: str) -> PublishedNetwork:
        network = self._reader.current(ibge_code)
        if network is None:
            raise NoSnapshotError(
                f"a cidade {ibge_code} não tem rede publicada; "
                f"rode `quantumco cidade processar {ibge_code}`"
            )
        return network


@dataclass(frozen=True, slots=True)
class CityView:
    """Cidade como o site a vê: nome, endereço do mapa e enquadramento."""

    ibge_code: str
    name: str
    uf: str
    slug: str
    status: str
    crs_epsg: int
    buffer_m: float
    bbox: tuple[float, float, float, float] | None  # oeste, sul, leste, norte (limite municipal)
    snapshot_id: str | None

    def to_json(self) -> dict[str, Any]:
        bbox = list(self.bbox) if self.bbox else None
        return {
            "ibge_code": self.ibge_code,
            "name": self.name,
            "uf": self.uf,
            "slug": self.slug,
            "status": self.status,
            "crs_epsg": self.crs_epsg,
            "buffer_m": self.buffer_m,
            "bbox": bbox,
            "center": (
                [round((bbox[0] + bbox[2]) / 2, 6), round((bbox[1] + bbox[3]) / 2, 6)]
                if bbox
                else None
            ),
            "snapshot_id": self.snapshot_id,
        }


class CityCatalogReader(Protocol):
    def cities(self) -> list[CityView]: ...


class NoCityError(LookupError):
    pass


class ListCities:
    """Cidades do cadastro; o site mostra só as publicadas."""

    def __init__(self, reader: CityCatalogReader) -> None:
        self._reader = reader

    def __call__(self, *, published_only: bool = True) -> list[CityView]:
        cities = self._reader.cities()
        return [c for c in cities if c.status == "publicada"] if published_only else cities

    def published(self, ibge_code: str) -> CityView:
        for city in self():
            if city.ibge_code == ibge_code:
                return city
        raise NoCityError(f"cidade {ibge_code} não está publicada")
