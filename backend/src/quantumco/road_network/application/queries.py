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
    def current(self) -> PublishedNetwork | None:
        """O snapshot mais recente, ou None se nenhum foi gerado ainda."""
        ...


class NoSnapshotError(LookupError):
    pass


class GetCurrentNetwork:
    def __init__(self, reader: PublishedNetworkReader) -> None:
        self._reader = reader

    def __call__(self) -> PublishedNetwork:
        network = self._reader.current()
        if network is None:
            raise NoSnapshotError(
                "nenhum snapshot disponível; rode o cold start: `quantumco snapshot build`"
            )
        return network
