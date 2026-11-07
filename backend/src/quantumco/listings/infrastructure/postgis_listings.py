"""Repositório do contexto listings no PostGIS: upsert idempotente (docs/adr/0003).

Cada página é uma transação: COPY para uma staging temporária → conta novos/mudados/iguais →
histórico só do que mudou → `INSERT … ON CONFLICT DO UPDATE` no estado atual. Rodar a mesma
página de novo não cria linha, versão nem mudança: só atualiza "visto agora".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

import psycopg
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.listings.application.ports import (
    MergeResult,
    Rejection,
    RunAlreadyActiveError,
    RunTally,
)
from quantumco.listings.domain.listing import SaleListing, SearchArea

# fatos copiados da staging para o estado atual (mesma ordem do COPY)
_FACTS = (
    "portal",
    "property_type",
    "usage_type",
    "usable_area_m2",
    "total_area_m2",
    "bedrooms",
    "bathrooms",
    "suites",
    "parking_spaces",
    "price_brl",
    "condo_fee_brl",
    "iptu_brl",
    "neighborhood",
    "street",
    "address_precision",
    "url",
    "photo_url",
)
_COLUMNS = ("source", "listing_id", *_FACTS, "lon", "lat", "content_hash", "facts", "seq")

_STAGE = """
create temp table stage (
    source text not null, listing_id text not null,
    portal text, property_type text, usage_type text,
    usable_area_m2 double precision, total_area_m2 double precision,
    bedrooms smallint, bathrooms smallint, suites smallint, parking_spaces smallint,
    price_brl numeric(14, 2), condo_fee_brl numeric(12, 2), iptu_brl numeric(12, 2),
    neighborhood text, street text, address_precision text, url text, photo_url text,
    lon double precision, lat double precision,
    content_hash text not null, facts jsonb not null, seq integer not null
) on commit drop
"""

# repetido dentro da página: fica a última ocorrência
_DEDUPE = """
delete from stage a using stage b
 where a.source = b.source and a.listing_id = b.listing_id and a.seq < b.seq
"""

_COUNT = """
select count(*) filter (where l.listing_id is null),
       count(*) filter (where l.listing_id is not null and l.content_hash <> s.content_hash),
       count(*) filter (where l.content_hash = s.content_hash)
  from stage s
  left join listings.sale_listings l on l.source = s.source and l.listing_id = s.listing_id
"""

_VERSIONS = """
insert into listings.sale_listing_versions
       (source, listing_id, valid_from, run_id, content_hash, facts)
select s.source, s.listing_id, now(), %(run)s, s.content_hash, s.facts
  from stage s
  left join listings.sale_listings l on l.source = s.source and l.listing_id = s.listing_id
 where l.content_hash is distinct from s.content_hash
on conflict do nothing
"""

_FACT_LIST = ", ".join(_FACTS)
_FACT_SET = ",\n    ".join(f"{column} = excluded.{column}" for column in _FACTS)
_UPSERT = f"""
insert into listings.sale_listings as l
       (source, listing_id, ibge_code, {_FACT_LIST}, geom, content_hash, last_run_id)
select source, listing_id, %(ibge)s, {_FACT_LIST},
       ST_SetSRID(ST_MakePoint(lon, lat), 4326), content_hash, %(run)s
  from stage
on conflict (source, listing_id) do update set
    ibge_code = excluded.ibge_code,
    {_FACT_SET},
    geom = excluded.geom,
    last_changed_at = case when l.content_hash is distinct from excluded.content_hash
                           then now() else l.last_changed_at end,
    content_hash = excluded.content_hash,
    last_seen_at = now(),
    last_run_id = excluded.last_run_id,
    removed_at = null
"""  # só nomes de coluna fixos deste módulo; os valores vão como parâmetros


def _row(item: SaleListing, seq: int) -> tuple[object, ...]:
    facts = [getattr(item, column) for column in _FACTS]
    return (
        item.source,
        item.listing_id,
        *facts,
        item.lon,
        item.lat,
        item.fingerprint(),
        Jsonb(item.facts()),
        seq,
    )


class PostgisListings:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def start_run(self, area: SearchArea, source: str) -> int:
        with self._pool.connection() as conn:
            conn.execute(
                "update listings.import_runs set status = 'erro', finished_at = now(), "
                "detail = 'abandonada: rodando havia mais de 6 h' "
                "where status = 'rodando' and source = %s and ibge_code = %s "
                "and started_at < now() - interval '6 hours'",
                (source, area.ibge_code),
            )
            try:
                row = conn.execute(
                    "insert into listings.import_runs (ibge_code, source) values (%s, %s) "
                    "returning run_id",
                    (area.ibge_code, source),
                ).fetchone()
            except psycopg.errors.UniqueViolation as exc:
                raise RunAlreadyActiveError(
                    f"já há uma carga de {source} rodando em {area.ibge_code}"
                ) from exc
        if row is None:
            raise RuntimeError("a carga não foi aberta")
        return int(row[0])

    def merge(self, run_id: int, area: SearchArea, listings: Sequence[SaleListing]) -> MergeResult:
        if not listings:
            return MergeResult()
        params = {"run": run_id, "ibge": area.ibge_code}
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(_STAGE)
            with conn.cursor().copy(f"copy stage ({', '.join(_COLUMNS)}) from stdin") as copy:
                for seq, item in enumerate(listings):
                    copy.write_row(_row(item, seq))
            conn.execute(_DEDUPE)
            counts = conn.execute(_COUNT).fetchone()
            conn.execute(_VERSIONS, params)
            conn.execute(_UPSERT, params)
        new, changed, unchanged = (int(v) for v in counts) if counts else (0, 0, 0)
        return MergeResult(new=new, changed=changed, unchanged=unchanged)

    def reject(self, run_id: int, rejections: Sequence[Rejection]) -> None:
        if not rejections:
            return
        seen: dict[str, list[str]] = defaultdict(list)
        rows = []
        for rejection in rejections:
            item = rejection.listing
            seen[item.source].append(item.listing_id)
            rows.append(
                (run_id, item.source, item.listing_id, list(rejection.reasons), Jsonb(item.facts()))
            )
        with self._pool.connection() as conn, conn.transaction():
            with conn.cursor() as cursor:
                cursor.executemany(
                    "insert into listings.rejected (run_id, source, listing_id, reasons, facts) "
                    "values (%s, %s, %s, %s, %s) on conflict do nothing",
                    rows,
                )
            # visto na fonte: a última versão boa fica como está, mas não conta como removido
            for source, ids in seen.items():
                conn.execute(
                    "update listings.sale_listings set last_seen_at = now(), last_run_id = %s, "
                    "removed_at = null where source = %s and listing_id = any(%s)",
                    (run_id, source, ids),
                )

    def mark_removed(self, run_id: int, area: SearchArea, source: str) -> int:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                "update listings.sale_listings set removed_at = now() "
                "where source = %s and ibge_code = %s and removed_at is null "
                "and last_run_id <> %s",
                (source, area.ibge_code, run_id),
            )
            return cursor.rowcount

    def progress(self, run_id: int, tally: RunTally) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                f"update listings.import_runs set {_TALLY_SET} where run_id = %s",
                (*_tally_values(tally), run_id),
            )

    def finish_run(self, run_id: int, status: str, tally: RunTally, detail: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update listings.import_runs set status = %s, finished_at = now(), "
                f"{_TALLY_SET}, detail = %s where run_id = %s",
                (status, *_tally_values(tally), detail[:2000], run_id),
            )


_TALLY_SET = (
    "complete = %s, pages = %s, received = %s, new = %s, changed = %s, unchanged = %s, "
    "rejected = %s, removed = %s, located = %s, attempts = %s, total = %s"
)


def _tally_values(tally: RunTally) -> tuple[object, ...]:
    return (
        tally.complete,
        tally.pages,
        tally.received,
        tally.new,
        tally.changed,
        tally.unchanged,
        tally.rejected,
        tally.removed,
        tally.located,
        tally.attempts,
        tally.total,
    )


# ---------------------------------------------------------------- leitura para o mapa

_MAP_FEATURES = """
select json_build_object(
    'type', 'FeatureCollection',
    'features', coalesce(json_agg(json_build_object(
        'type', 'Feature',
        'geometry', ST_AsGeoJSON(l.geom, 6)::json,
        'properties', json_build_object(
            'id', l.listing_id,
            'portal', l.portal,
            'property_type', l.property_type,
            'usage_type', l.usage_type,
            'usable_area_m2', l.usable_area_m2,
            'total_area_m2', l.total_area_m2,
            'bedrooms', l.bedrooms,
            'bathrooms', l.bathrooms,
            'suites', l.suites,
            'parking_spaces', l.parking_spaces,
            'price_brl', l.price_brl,
            'condo_fee_brl', l.condo_fee_brl,
            'iptu_brl', l.iptu_brl,
            'neighborhood', l.neighborhood,
            'street', l.street,
            'url', l.url,
            'photo_url', l.photo_url,
            'seen', to_char(l.last_seen_at at time zone 'America/Sao_Paulo', 'YYYY-MM-DD')
        )
    )), '[]'::json)
)
from (
    select *
      from listings.sale_listings
     where ibge_code = %s and removed_at is null and geom is not null
     order by last_seen_at desc, listing_id
     limit %s
) l
"""


class PostgisListingMap:
    """Os anúncios ativos com ponto, prontos para o mapa (usa o índice GiST parcial)."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def features(self, ibge_code: str, limit: int) -> dict[str, object]:
        with self._pool.connection() as conn:
            row = conn.execute(_MAP_FEATURES, (ibge_code, limit)).fetchone()
        collection = row[0] if row else None
        return (
            collection
            if isinstance(collection, dict)
            else {"type": "FeatureCollection", "features": []}
        )
