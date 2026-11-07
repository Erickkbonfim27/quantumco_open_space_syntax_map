"""Imóveis à venda para o mapa (docs/adr/0003): atrás da flag, só os ativos com ponto."""

from __future__ import annotations

from typing import Any, Protocol

from quantumco.listings.application.ports import FeatureDisabledError, FeatureFlags
from quantumco.listings.domain.listing import FLAG_GLUE_API

MAX_FEATURES = 20_000  # teto de pontos por cidade numa resposta (o mapa desenha todos)


class ListingMapReader(Protocol):
    def features(self, ibge_code: str, limit: int) -> dict[str, Any]:
        """GeoJSON (FeatureCollection) dos anúncios ativos com ponto, os mais recentes primeiro."""
        ...


class ListingsForMap:
    def __init__(
        self,
        flags: FeatureFlags,
        reader: ListingMapReader,
        flag: str = FLAG_GLUE_API,
        limit: int = MAX_FEATURES,
    ) -> None:
        self._flags = flags
        self._reader = reader
        self._flag = flag
        self._limit = limit

    def __call__(self, ibge_code: str) -> dict[str, Any]:
        if not self._flags.is_enabled(self._flag):
            raise FeatureDisabledError(f"camada de imóveis desligada (flag {self._flag})")
        return self._reader.features(ibge_code, self._limit)
