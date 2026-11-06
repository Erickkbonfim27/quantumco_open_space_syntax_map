"""Camadas territoriais no PostGIS (schema `territory`): gravação por COPY e recorte por área."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from psycopg import errors
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.territory.application.ports import (
    NamedPlace,
    PlaceCount,
    PolygonOverlaps,
    Ring,
)
from quantumco.territory.domain.addresses import AddressHit
from quantumco.territory.domain.profile import TractOverlap, ZoneOverlap
from quantumco.territory.domain.records import LayerData

log = logging.getLogger(__name__)

SRID = 31982
_GEOM = (
    "ST_Multi(ST_CollectionExtract(ST_MakeValid("
    f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(g), 4326), {SRID})), 3))"
)


class PostgisTerritoryRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def replace(self, data: LayerData, fetched_at: datetime) -> None:
        with self._pool.connection() as conn, conn.transaction():
            if data.tracts:
                conn.execute("delete from territory.tracts")
                conn.execute(
                    "create temp table stage (code text, attrs jsonb, g text) on commit drop"
                )
                with conn.cursor().copy("copy stage (code, attrs, g) from stdin") as copy:
                    for t in data.tracts:
                        copy.write_row((t.code, Jsonb(dict(t.attrs)), json.dumps(t.geometry)))
                conn.execute(
                    "insert into territory.tracts (code, attrs, area_m2, geom) "
                    "select code, attrs, ST_Area(geom), geom from "
                    f"(select code, attrs, {_GEOM} geom from stage) s"
                )
            if data.zones:
                conn.execute("delete from territory.zones where layer = %s", (data.layer,))
                conn.execute(
                    "create temp table stage_z (layer text, category text, process text, "
                    "attrs jsonb, g text) on commit drop"
                )
                with conn.cursor().copy(
                    "copy stage_z (layer, category, process, attrs, g) from stdin"
                ) as copy:
                    for z in data.zones:
                        copy.write_row(
                            (
                                z.layer,
                                z.category,
                                z.process,
                                Jsonb(dict(z.attrs)),
                                json.dumps(z.geometry),
                            )
                        )
                conn.execute(
                    "insert into territory.zones (layer, category, process, attrs, area_m2, geom) "
                    "select layer, category, process, attrs, ST_Area(geom), geom from "
                    f"(select layer, category, process, attrs, {_GEOM} geom from stage_z) s "
                    "where not ST_IsEmpty(geom)"
                )
            if data.places:
                conn.execute("delete from territory.places where layer = %s", (data.layer,))
                conn.execute(
                    "create temp table stage_p (layer text, kind text, name text, tract_code text, "
                    "attrs jsonb, lon double precision, lat double precision) on commit drop"
                )
                with conn.cursor().copy(
                    "copy stage_p (layer, kind, name, tract_code, attrs, lon, lat) from stdin"
                ) as copy:
                    for p in data.places:
                        copy.write_row(
                            (
                                p.layer,
                                p.kind,
                                p.name,
                                p.tract_code,
                                Jsonb(dict(p.attrs)),
                                p.lon,
                                p.lat,
                            )
                        )
                conn.execute(
                    "insert into territory.places (layer, kind, name, tract_code, attrs, geom) "
                    "select layer, kind, name, tract_code, attrs, "
                    f"ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), {SRID}) from stage_p"
                )
            if data.addresses:
                conn.execute("delete from territory.addresses")
                with conn.cursor().copy(
                    "copy territory.addresses (street, number, locality, cep, units, search_key, "
                    "lon, lat) from stdin"
                ) as copy:
                    for a in data.addresses:
                        copy.write_row(
                            (a.street, a.number, a.locality, a.cep, a.units, a.search_key,
                             a.lon, a.lat)
                        )  # fmt: skip
            conn.execute(
                "insert into territory.layers "
                "(layer, source, source_url, license, rows, fetched_at, meta) "
                "values (%s, %s, %s, %s, %s, %s, %s) on conflict (layer) do update set "
                "source = excluded.source, source_url = excluded.source_url, "
                "license = excluded.license, rows = excluded.rows, "
                "fetched_at = excluded.fetched_at, meta = excluded.meta",
                (data.layer, data.source, data.source_url, data.license, data.rows, fetched_at,
                 Jsonb(dict(data.meta))),
            )  # fmt: skip
        conn_note = (
            "setores"
            if data.tracts
            else "zonas"
            if data.zones
            else "endereços"
            if data.addresses
            else "pontos"
        )
        log.info("  %s: %d %s substituídos", data.layer, data.rows, conn_note)

    def layers(self) -> Sequence[Mapping[str, Any]]:
        return _layers(self._pool)


def _layers(pool: ConnectionPool) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        try:
            rows = conn.execute(
                "select layer, source, source_url, license, rows, fetched_at from territory.layers "
                "order by layer"
            ).fetchall()
        except errors.UndefinedTable:
            return []
    return [
        {"layer": r[0], "source": r[1], "source_url": r[2], "license": r[3], "rows": r[4],
         "fetched_at": r[5].isoformat()}
        for r in rows
    ]  # fmt: skip


_POLY = (
    "with poly as (select ST_MakeValid(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(g)s), 4326), "
    f"{SRID})) g)"
)

_TRACTS = f"""{_POLY}
select t.code, t.attrs, ST_Area(ST_Intersection(t.geom, poly.g)) / nullif(t.area_m2, 0),
       coalesce(d.inside, 0), coalesce(d.total, 0)
from territory.tracts t
cross join poly
left join lateral (
    select count(*) total, count(*) filter (where ST_Intersects(p.geom, poly.g)) inside
    from territory.places p
    where p.layer = 'cnefe' and p.kind = 'domicilio' and p.tract_code = t.code
) d on true
where ST_Intersects(t.geom, poly.g)
"""

_ZONES = f"""{_POLY}
select z.layer, z.category, z.process, z.attrs, ST_Area(ST_Intersection(z.geom, poly.g)), z.area_m2
from territory.zones z, poly
where ST_Intersects(z.geom, poly.g)
"""

_COUNTS = f"""{_POLY}
select p.layer, p.kind, count(*), count(*) filter (where (p.attrs ->> 'sus')::boolean)
from territory.places p, poly
where ST_Intersects(p.geom, poly.g)
group by 1, 2
"""

_NAMED = f"""{_POLY}
select distinct p.layer, p.kind, p.name
from territory.places p, poly
where p.name is not null
  and ((p.layer = 'cnefe' and p.kind = 'ensino')
       or (p.layer = 'cnes' and p.kind in ('atencao_basica', 'hospital', 'urgencia')))
  and ST_Intersects(p.geom, poly.g)
order by p.layer, p.kind, p.name
limit 200
"""


# Amostra estável (mesmo polígono → mesmos pontos): ordena por hash do id.
_POINTS = f"""{_POLY},
inside as (
    select p.place_id, p.layer, p.kind, p.geom from territory.places p, poly
    where ST_Intersects(p.geom, poly.g)
),
ranked as (
    select *, row_number() over (
        partition by (layer = 'cnefe' and kind = 'domicilio'),
                     (layer = 'cnefe' and kind = 'outras_finalidades')
        order by md5(place_id::text)
    ) n,
    case when layer = 'cnefe' and kind = 'domicilio' then 1500
         when layer = 'cnefe' and kind = 'outras_finalidades' then 800
         else 1200 end cap
    from inside
)
select ST_X(ST_Transform(geom, 4326)), ST_Y(ST_Transform(geom, 4326)), layer || ':' || kind
from ranked where n <= cap
"""

_ZONE_SHAPES = f"""{_POLY}
select z.layer, z.category, ST_AsGeoJSON(ST_Transform(ST_SimplifyPreserveTopology(
           ST_Intersection(z.geom, poly.g), 2), 4326), 6)::json
from territory.zones z, poly
where z.layer in ('risco', 'suscet_inundacao')
  and not (z.layer = 'suscet_inundacao' and z.category = 'Baixa')
  and ST_Intersects(z.geom, poly.g)
"""


_FC = (
    "select json_build_object('type', 'FeatureCollection', 'features', "
    "coalesce(json_agg(f.feature), '[]'))::text from ({}) f"
)
_FEATURE = (
    "json_build_object('type', 'Feature', 'geometry', ST_AsGeoJSON({geom}, 6)::json, "
    "'properties', {props}) as feature"
)
_MAP_LAYERS = {
    "risco": _FEATURE.format(
        geom="ST_Transform(geom, 4326)",
        props="json_build_object('categoria', category, 'processo', process, "
        "'pessoas', attrs -> 'people', 'local', attrs -> 'place', 'data', attrs -> 'date')",
    )
    + " from territory.zones where layer = 'risco'",
    "suscet_inundacao": _FEATURE.format(
        geom="ST_Transform(ST_SimplifyPreserveTopology(geom, 3), 4326)",
        props="json_build_object('categoria', category)",
    )
    + " from territory.zones where layer = 'suscet_inundacao' and category in ('Alta', 'Média')",
    "saude": _FEATURE.format(
        geom="ST_Transform(geom, 4326)",
        props="json_build_object('tipo', kind, 'nome', name, 'sus', attrs -> 'sus')",
    )
    + " from territory.places where layer = 'cnes'",
    "escolas": _FEATURE.format(
        geom="ST_Transform(geom, 4326)", props="json_build_object('nome', name)"
    )
    + " from territory.places where layer = 'cnefe' and kind = 'ensino'",
}


class PostgisTerritoryReader:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        # as camadas só mudam no `territory import`: cache por data de importação
        self._cache: dict[str, tuple[str, bytes]] = {}

    def map_layer(self, name: str) -> bytes | None:
        source = {"saude": "cnes", "escolas": "cnefe"}.get(name, name)
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select fetched_at::text from territory.layers where layer = %s", (source,)
                ).fetchone()
            except errors.UndefinedTable:
                return None
            if row is None:
                return None
            cached = self._cache.get(name)
            if cached and cached[0] == row[0]:
                return cached[1]
            (text,) = conn.execute(_FC.format(f"select {_MAP_LAYERS[name]}")).fetchone()  # type: ignore[misc]
        data = str(text).encode()
        self._cache[name] = (row[0], data)
        log.info("camada %s para o mapa: %.0f kB", name, len(data) / 1024)
        return data

    def layers(self) -> Sequence[Mapping[str, Any]]:
        return _layers(self._pool)

    def overlaps(self, ring: Ring) -> PolygonOverlaps | None:
        closed = list(ring) if ring[0] == ring[-1] else [*ring, ring[0]]
        params = {"g": json.dumps({"type": "Polygon", "coordinates": [closed]})}
        with self._pool.connection() as conn:
            try:
                if conn.execute("select 1 from territory.layers limit 1").fetchone() is None:
                    return None
            except errors.UndefinedTable:
                return None
            (area_m2,) = conn.execute(f"{_POLY} select ST_Area(g) from poly", params).fetchone()  # type: ignore[misc]
            tracts = conn.execute(_TRACTS, params).fetchall()
            zones = conn.execute(_ZONES, params).fetchall()
            counts = conn.execute(_COUNTS, params).fetchall()
            named = conn.execute(_NAMED, params).fetchall()
            points = conn.execute(_POINTS, params).fetchall()
            shapes = conn.execute(_ZONE_SHAPES, params).fetchall()
        return PolygonOverlaps(
            area_m2=float(area_m2),
            tracts=[
                TractOverlap(
                    code=r[0],
                    attrs=r[1],
                    area_share=float(r[2] or 0),
                    addresses_in=int(r[3]),
                    addresses_all=int(r[4]),
                )
                for r in tracts
            ],
            zones=[
                ZoneOverlap(
                    layer=r[0],
                    category=r[1],
                    process=r[2],
                    attrs=r[3],
                    area_in_m2=float(r[4]),
                    area_total_m2=float(r[5]),
                )
                for r in zones
            ],
            place_counts=[PlaceCount(r[0], r[1], int(r[2]), int(r[3])) for r in counts],
            named_places=[NamedPlace(r[0], r[1], r[2]) for r in named],
            points=[(round(float(r[0]), 6), round(float(r[1]), 6), r[2]) for r in points],
            zone_shapes=[{"layer": r[0], "category": r[1], "geometry": r[2]} for r in shapes],
        )


class PostgisAddressIndex:
    """Busca no índice de endereços: todas as palavras no nome do logradouro (sem acento)."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def candidates(self, words: Sequence[str], limit: int = 600) -> list[AddressHit]:
        if not words:
            return []
        where = " and ".join(["search_key like %s"] * len(words))
        params: list[object] = [f"%{w}%" for w in words]
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(
                    "select street, number, locality, cep, lon, lat, units "
                    f"from territory.addresses where {where} order by length(search_key) "
                    "limit %s",
                    [*params, limit],
                ).fetchall()
            except errors.UndefinedTable:
                return []
        return [AddressHit(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]
