"""Idempotência do upsert de imóveis à venda no PostGIS (ADR 0003) e as feature flags.

Rodar com: QC_TEST_DATABASE_URL=postgresql://…/quantumco_test uv run pytest -m db
(o banco temporário em contêiner está descrito em test_postgis_territory.py)

Recria só o schema `listings` e a tabela de flags: roda apenas num banco cujo nome contém "test".
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest
from psycopg_pool import ConnectionPool

from quantumco.listings.application.ports import Rejection, RunAlreadyActiveError, RunTally
from quantumco.listings.domain.listing import SaleListing, SearchArea
from quantumco.listings.infrastructure.postgis_listings import PostgisListings
from quantumco.platform.feature_flags import PostgresFeatureFlags
from quantumco.platform.postgres import MIGRATIONS_DIR, connect, migrate, pool

URL = os.environ.get("QC_TEST_DATABASE_URL", "")
pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not URL, reason="QC_TEST_DATABASE_URL não definido"),
]
MIGRATIONS = ["013_flags_listings", "014_listings_photo"]
BRUSQUE = SearchArea("4202909", "Brusque", "SC")
SOURCE = "grupo-olx"
PRICE_OF_1 = "select price_brl from listings.sale_listings where listing_id = '1'"


def listing(listing_id: str, **changes: Any) -> SaleListing:
    base = SaleListing(
        source=SOURCE,
        listing_id=listing_id,
        portal="zap",
        city="Brusque",
        property_type="APARTMENT",
        usable_area_m2=70.0,
        bedrooms=2,
        price_brl=450_000.0,
        neighborhood="Centro",
        address_precision="ALL",
        lon=-48.917,
        lat=-27.098,
        url=f"https://www.zapimoveis.com.br/imovel/{listing_id}",
        photo_url=f"https://resizedimgs.vivareal.com/{listing_id}.jpg",
    )
    return replace(base, **changes)


@pytest.fixture
def db() -> Iterator[ConnectionPool]:
    with connect(URL) as conn:
        name = conn.execute("select current_database()").fetchone()
        assert name is not None
        if "test" not in str(name[0]):
            pytest.skip(f"banco {name[0]!r} não parece de teste; recuso recriar schemas")
        conn.execute("create extension if not exists postgis")
        conn.execute("drop schema if exists listings cascade")
        conn.execute("drop table if exists public.feature_flags")
        conn.execute(
            "create table if not exists public.schema_migrations "
            "(version text primary key, applied_at timestamptz not null default now())"
        )
        conn.execute("delete from public.schema_migrations where version = any(%s)", (MIGRATIONS,))
        conn.commit()
    assert migrate(URL, only=set(MIGRATIONS)) == MIGRATIONS
    p = pool(URL)
    yield p
    p.close()


def scalar(p: ConnectionPool, query: str, *params: object) -> Any:
    with p.connection() as conn:
        row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


def full_run(repo: PostgisListings, listings: list[SaleListing]) -> tuple[int, Any, int]:
    run_id = repo.start_run(BRUSQUE, SOURCE)
    merged = repo.merge(run_id, BRUSQUE, listings)
    removed = repo.mark_removed(run_id, BRUSQUE, SOURCE)
    repo.finish_run(run_id, "ok", RunTally(complete=True), "")
    return run_id, merged, removed


def test_migration_can_run_twice(db: ConnectionPool) -> None:
    for version in MIGRATIONS:
        sql = (MIGRATIONS_DIR / f"{version}.sql").read_text(encoding="utf-8")
        with connect(URL) as conn:
            conn.execute(sql.encode())  # homologação pode já ter as tabelas: não pode falhar
            conn.commit()


def test_cover_photo_link_is_kept_but_is_not_a_change(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    full_run(repo, [listing("1")])
    _, again, _ = full_run(repo, [listing("1", photo_url="https://outro-servidor/1.jpg")])
    assert (again.changed, again.unchanged) == (0, 1)
    photo = "select photo_url from listings.sale_listings where listing_id = '1'"
    assert scalar(db, photo) == "https://outro-servidor/1.jpg"


def test_same_data_twice_changes_nothing(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    street_only = listing("3", lon=None, lat=None, address_precision="STREET")
    data = [listing("1"), listing("2"), street_only]
    _, first, _ = full_run(repo, data)
    assert (first.new, first.changed, first.unchanged) == (3, 0, 0)
    changed_at_query = "select last_changed_at from listings.sale_listings where listing_id = '1'"
    changed_at = scalar(db, changed_at_query)

    _, second, removed = full_run(repo, data)
    assert (second.new, second.changed, second.unchanged) == (0, 0, 3)
    assert removed == 0
    assert scalar(db, "select count(*) from listings.sale_listings") == 3
    assert scalar(db, "select count(*) from listings.sale_listing_versions") == 3
    assert scalar(db, changed_at_query) == changed_at
    assert scalar(db, "select count(*) from listings.sale_listings where geom is not null") == 2


def test_duplicates_in_a_page_become_one_row(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    run_id = repo.start_run(BRUSQUE, SOURCE)
    result = repo.merge(run_id, BRUSQUE, [listing("1"), listing("1", price_brl=460_000.0)])
    assert result.new == 1
    assert scalar(db, PRICE_OF_1) == 460_000


def test_a_real_change_updates_and_keeps_history(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    full_run(repo, [listing("1")])
    # outro portal, mesmo imóvel: não é mudança
    _, same, _ = full_run(repo, [listing("1", portal="vivareal", url="https://vivareal/x")])
    assert (same.changed, same.unchanged) == (0, 1)
    _, cheaper, _ = full_run(repo, [listing("1", price_brl=430_000.0)])
    assert cheaper.changed == 1
    assert scalar(db, PRICE_OF_1) == 430_000
    prices = scalar(
        db,
        "select array_agg((facts->>'price_brl')::numeric order by valid_from) "
        "from listings.sale_listing_versions where listing_id = '1'",
    )
    assert prices == [450_000, 430_000]


def test_bad_data_never_overwrites_good_data(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    full_run(repo, [listing("1")])
    run_id = repo.start_run(BRUSQUE, SOURCE)
    repo.reject(run_id, [Rejection(listing("1", price_brl=-1.0), ("preço fora da faixa",))])
    repo.reject(run_id, [Rejection(listing("1", price_brl=-1.0), ("preço fora da faixa",))])
    removed = repo.mark_removed(run_id, BRUSQUE, SOURCE)
    repo.finish_run(run_id, "ok", RunTally(complete=True), "")
    assert removed == 0  # visto na fonte, mesmo com dado ruim: não some do mapa
    assert scalar(db, PRICE_OF_1) == 450_000
    assert scalar(db, "select count(*) from listings.rejected") == 1  # repetir não duplica


def test_removed_only_after_a_complete_run_and_comes_back(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    full_run(repo, [listing("1"), listing("2")])
    _, _, removed = full_run(repo, [listing("1")])
    assert removed == 1
    active = "select count(*) from listings.sale_listings where removed_at is null"
    assert scalar(db, active) == 1
    assert scalar(db, "select count(*) from listings.sale_listings") == 2  # nada é apagado
    full_run(repo, [listing("1"), listing("2")])
    assert scalar(db, active) == 2


def test_one_active_run_per_source_and_city(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    run_id = repo.start_run(BRUSQUE, SOURCE)
    with pytest.raises(RunAlreadyActiveError):
        repo.start_run(BRUSQUE, SOURCE)
    repo.finish_run(run_id, "bloqueado", RunTally(attempts=1), "HTTP 403")
    assert repo.start_run(BRUSQUE, SOURCE) > run_id


def test_progress_is_visible_while_the_run_is_going(db: ConnectionPool) -> None:
    repo = PostgisListings(db)
    run_id = repo.start_run(BRUSQUE, SOURCE)
    repo.progress(run_id, RunTally(pages=3, received=90, new=80, unchanged=10, total=2830))
    row = "select status, pages, received, new, total from listings.import_runs where run_id = %s"
    with db.connection() as conn:
        assert conn.execute(row, (run_id,)).fetchone() == ("rodando", 3, 90, 80, 2830)


def test_feature_flags(db: ConnectionPool) -> None:
    flags = PostgresFeatureFlags(db)
    assert flags.is_enabled("listings_glue_api") is False  # nasce desligada
    assert flags.is_enabled("nao_existe") is False
    flags.set("listings_glue_api", True)
    assert flags.is_enabled("listings_glue_api") is True
    flags.set("listings_glue_api", False)
    assert [f.name for f in flags.all()] == ["listings_glue_api"]
