"""Montagem do contexto `listings` (imóveis à venda, docs/adr/0003) e das feature flags."""

from __future__ import annotations

import logging
import os

from quantumco.bootstrap.cities import city_view
from quantumco.bootstrap.settings import Settings
from quantumco.listings.application.import_listings import ImportSaleListings
from quantumco.listings.application.queries import ListingsForMap
from quantumco.listings.domain.listing import FLAG_GLUE_API, SearchArea
from quantumco.listings.infrastructure.glue_api import USER_AGENT, GlueApiListings
from quantumco.listings.infrastructure.postgis_listings import PostgisListingMap, PostgisListings
from quantumco.platform.feature_flags import PostgresFeatureFlags
from quantumco.platform.postgres import migrate, shared_pool
from quantumco.shared_kernel.city import expand_bbox

log = logging.getLogger(__name__)

LISTINGS_MIGRATIONS = frozenset({"013_flags_listings", "014_listings_photo"})
# folga sobre o retângulo do município: ponto de anúncio costuma vir com erro de geocodificação
BBOX_SLACK_M = 1_000.0


def ensure_schema(settings: Settings) -> list[str]:
    """Aplica SÓ as migrações das flags e dos anúncios: não leva junto as de outro trabalho."""
    return migrate(settings.require_database(), only=LISTINGS_MIGRATIONS)


def feature_flags(settings: Settings) -> PostgresFeatureFlags:
    return PostgresFeatureFlags(shared_pool(settings.require_database()))


def search_area(settings: Settings, ibge_code: str) -> SearchArea:
    """A cidade do cadastro (ADR 0002) → onde buscar. `CityNotReadyError` se não cadastrada."""
    city = city_view(settings, ibge_code)
    bbox = expand_bbox(city.bbox, BBOX_SLACK_M) if city.bbox else None
    return SearchArea(ibge_code=city.ibge_code, city=city.name, uf=city.uf, bbox=bbox)


def listings_user_agent() -> str:
    """User-Agent dos pedidos: `QC_LISTINGS_USER_AGENT` do `.env` (fora do repositório) ou o
    da quantumco. A troca é decisão do dono, para a prova de conceito (docs/adr/0003)."""
    custom = os.environ.get("QC_LISTINGS_USER_AGENT", "").strip()
    if custom:
        log.warning("User-Agent da glue-api vem de QC_LISTINGS_USER_AGENT (não é o da quantumco)")
    return custom or USER_AGENT


def import_listings_use_case(settings: Settings, portal: str, delay_s: float) -> ImportSaleListings:
    pool = shared_pool(settings.require_database())
    return ImportSaleListings(
        flags=PostgresFeatureFlags(pool),
        source=GlueApiListings(portal=portal, delay_s=delay_s, user_agent=listings_user_agent()),
        repository=PostgisListings(pool),
        flag=FLAG_GLUE_API,
    )


def listings_map_query(settings: Settings) -> ListingsForMap:
    """Anúncios para o mapa: lê a flag a cada pedido (desligar vale na hora)."""
    pool = shared_pool(settings.require_database())
    return ListingsForMap(flags=PostgresFeatureFlags(pool), reader=PostgisListingMap(pool))
