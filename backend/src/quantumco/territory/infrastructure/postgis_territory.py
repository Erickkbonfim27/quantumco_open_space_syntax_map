"""Camadas territoriais no PostGIS (schema `territory`): gravação por COPY e recorte por área."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection, errors
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.territory.application.ports import (
    NamedPlace,
    PlaceCount,
    PolygonOverlaps,
    Ring,
)
from quantumco.territory.domain.addresses import AddressHit
from quantumco.territory.domain.grid import BRUSQUE_GRID, BUFFER_M
from quantumco.territory.domain.profile import (
    BUILDINGS_LAYER,
    BuildingStats,
    GridStat,
    TractOverlap,
    ZoneOverlap,
)
from quantumco.territory.domain.records import GridKind, GridLayer, LayerData

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
            if data.buildings:
                _replace_buildings(conn, data)
            meta = dict(data.meta)
            if data.grid is not None:
                meta |= _replace_grid(conn, data.layer, data.grid)
            conn.execute(
                "insert into territory.layers "
                "(layer, source, source_url, license, rows, fetched_at, meta) "
                "values (%s, %s, %s, %s, %s, %s, %s) on conflict (layer) do update set "
                "source = excluded.source, source_url = excluded.source_url, "
                "license = excluded.license, rows = excluded.rows, "
                "fetched_at = excluded.fetched_at, meta = excluded.meta",
                (data.layer, data.source, data.source_url, data.license, data.rows, fetched_at,
                 Jsonb(meta)),
            )  # fmt: skip
        conn_note = (
            "setores"
            if data.tracts
            else "zonas"
            if data.zones
            else "endereços"
            if data.addresses
            else "edificações"
            if data.buildings
            else "células"
            if data.grid is not None
            else "pontos"
        )
        log.info("  %s: %d %s substituídos", data.layer, data.rows, conn_note)

    def layers(self) -> Sequence[Mapping[str, Any]]:
        return _layers(self._pool)


def _replace_buildings(conn: Connection[Any], data: LayerData) -> None:
    conn.execute("delete from territory.buildings")
    conn.execute(
        "create temp table stage_b (building_id text, source text, height_m real, "
        "floors smallint, class text, confidence real, g text) on commit drop"
    )
    with conn.cursor().copy(
        "copy stage_b (building_id, source, height_m, floors, class, confidence, g) from stdin"
    ) as copy:
        for b in data.buildings:
            copy.write_row(
                (b.building_id, b.source, b.height_m, b.floors, b.klass, b.confidence,
                 json.dumps(b.geometry))
            )  # fmt: skip
    conn.execute(
        "insert into territory.buildings "
        "(building_id, source, height_m, floors, class, confidence, area_m2, geom) "
        "select building_id, source, height_m, floors, class, confidence, ST_Area(geom), geom "
        "from (select building_id, source, height_m, floors, class, confidence, "
        f"{_GEOM} geom from stage_b) s "
        "where not ST_IsEmpty(geom) on conflict (building_id) do nothing"
    )


# Células da grade: só as que ficam a até BUFFER_M do município (união dos setores do IBGE).
# O município é subdividido e indexado para o teste ponto-em-polígono não varrer a união inteira.
_GRID_AREA = (
    "create temp table grid_area on commit drop as "
    f"select ST_Subdivide(ST_Buffer(ST_Union(geom), {BUFFER_M}), 128) g from territory.tracts"
)
_GRID_CELLS = f"""
insert into territory.grid (cell, geom)
select p.cell, p.geom
from (
    select r * {BRUSQUE_GRID.ncols} + c cell,
           ST_SetSRID(ST_MakePoint({BRUSQUE_GRID.west} + (c + 0.5) * {BRUSQUE_GRID.size},
                                   {BRUSQUE_GRID.north} - (r + 0.5) * {BRUSQUE_GRID.size}),
                      {SRID}) geom
    from generate_series(0, {BRUSQUE_GRID.nrows - 1}) r,
         generate_series(0, {BRUSQUE_GRID.ncols - 1}) c
) p
where exists (select 1 from grid_area a where ST_Intersects(a.g, p.geom))
on conflict (cell) do nothing
"""


def _ensure_grid(conn: Connection[Any]) -> None:
    if conn.execute("select 1 from territory.grid limit 1").fetchone() is not None:
        return
    if conn.execute("select 1 from territory.tracts limit 1").fetchone() is None:
        raise RuntimeError(
            "a grade de 30 m é recortada pelo município: importe os setores antes "
            "(`quantumco territory import --only ibge-setores`)"
        )
    started = time.perf_counter()
    conn.execute(_GRID_AREA)
    conn.execute("create index on grid_area using gist (g)")
    conn.execute(_GRID_CELLS)
    (cells,) = conn.execute("select count(*) from territory.grid").fetchone()  # type: ignore[misc]
    log.info("  grade de 30 m criada: %d células em %.1fs", cells, time.perf_counter() - started)


def _replace_grid(conn: Connection[Any], layer: str, grid: GridLayer) -> dict[str, Any]:
    """Grava os valores de uma camada na grade e devolve o que vai para `territory.layers.meta`."""
    _ensure_grid(conn)
    conn.execute("delete from territory.grid_values where layer = %s", (layer,))
    conn.execute("create temp table stage_g (cell bigint, value real) on commit drop")
    with conn.cursor().copy("copy stage_g (cell, value) from stdin") as copy:
        for cell, value in grid.values.items():
            if math.isfinite(value):
                copy.write_row((cell, value))
    inserted = conn.execute(
        "insert into territory.grid_values (layer, cell, value) "
        "select %s, s.cell, s.value from stage_g s join territory.grid g on g.cell = s.cell",
        (layer,),
    ).rowcount
    outside = len(grid.values) - inserted
    if outside:
        log.info("  %s: %d células fora do município (ou sem valor) descartadas", layer, outside)
    if grid.image is None:
        conn.execute("delete from territory.images where layer = %s", (layer,))
    else:
        img = grid.image
        conn.execute(
            "insert into territory.images (layer, png, bounds, legend) values (%s, %s, %s, %s) "
            "on conflict (layer) do update set png = excluded.png, bounds = excluded.bounds, "
            "legend = excluded.legend",
            (layer, img.png, list(img.bounds),
             Jsonb([{"label": i.label, "color": i.color} for i in img.legend])),
        )  # fmt: skip
    return {"grid_kind": grid.kind.value, "grid_unit": grid.unit, "grid_cells": inserted}


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


# Grade de 30 m: centros de célula dentro do polígono.
_GRID_INSIDE = f"""{_POLY},
inside as (select g.cell from territory.grid g, poly where ST_Intersects(g.geom, poly.g))"""

_GRID_CONTINUOUS = f"""{_GRID_INSIDE}
select v.layer, count(*), avg(v.value), min(v.value), max(v.value),
       percentile_cont(array[0.1, 0.5, 0.9]) within group (order by v.value)
from inside i join territory.grid_values v on v.cell = i.cell
where v.layer = any(%(layers)s)
group by v.layer
"""

_GRID_CATEGORICAL = f"""{_GRID_INSIDE}
select v.layer, v.value, count(*)
from inside i join territory.grid_values v on v.cell = i.cell
where v.layer = any(%(layers)s)
group by v.layer, v.value
"""

# Contagem e altura pelo ponto interno da pegada; área pela pegada recortada.
_BUILDINGS = f"""{_POLY},
b as (
    select b.source, b.height_m, ST_Area(ST_Intersection(b.geom, poly.g)) a,
           ST_Intersects(ST_PointOnSurface(b.geom), poly.g) inside
    from territory.buildings b, poly
    where ST_Intersects(b.geom, poly.g)
)
select source, count(*) filter (where inside), coalesce(sum(a), 0),
       count(height_m) filter (where inside), coalesce(sum(height_m) filter (where inside), 0)
from b group by source
"""

# Amostra estável (mesmo polígono → mesmos prédios) para o desenho do nível no painel.
BUILDING_SAMPLE = 2500
_BUILDING_POINTS = f"""{_POLY}
select ST_X(p), ST_Y(p), area_m2, source = 'OpenStreetMap'
from (
    select ST_Transform(ST_PointOnSurface(b.geom), 4326) p, b.area_m2, b.source, b.building_id
    from territory.buildings b, poly
    where b.geom && poly.g and ST_Intersects(ST_PointOnSurface(b.geom), poly.g)
    order by md5(b.building_id)
    limit {BUILDING_SAMPLE}
) s
"""

_BUILDING_TILE = f"""
select coalesce(ST_AsMVT(t, '{BUILDINGS_LAYER}', 4096, 'geom'), '')
from (
    select b.source, b.height_m, b.floors, round(b.area_m2) area_m2,
           round(b.confidence::numeric, 2)::real confidence,
           ST_AsMVTGeom(ST_Transform(b.geom, 3857), ST_TileEnvelope(%(z)s, %(x)s, %(y)s),
                        4096, 64, true) geom
    from territory.buildings b
    where b.geom && ST_Transform(
        ST_TileEnvelope(%(z)s, %(x)s, %(y)s, margin => 64.0 / 4096), {SRID})
) t
where t.geom is not null
"""


def _grid_stats(
    conn: Connection[Any], params: dict[str, Any], kinds: Mapping[str, str]
) -> list[GridStat]:
    continuous = [k for k, v in kinds.items() if v == GridKind.CONTINUOUS.value]
    categorical = [k for k, v in kinds.items() if v == GridKind.CATEGORICAL.value]
    stats: list[GridStat] = []
    if continuous:
        for r in conn.execute(_GRID_CONTINUOUS, {**params, "layers": continuous}).fetchall():
            p10, p50, p90 = r[5] or (None, None, None)
            stats.append(
                GridStat(
                    r[0], GridKind.CONTINUOUS.value, int(r[1]), r[2], r[3], r[4], p10, p50, p90
                )
            )
    if categorical:
        hist: dict[str, dict[float, int]] = {}
        for layer, value, n in conn.execute(
            _GRID_CATEGORICAL, {**params, "layers": categorical}
        ).fetchall():
            hist.setdefault(layer, {})[float(value)] = int(n)
        stats.extend(
            GridStat(layer, GridKind.CATEGORICAL.value, sum(h.values()), histogram=h)
            for layer, h in hist.items()
        )
    return sorted(stats, key=lambda s: s.layer)


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

    def images(self) -> Sequence[Mapping[str, Any]]:
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(
                    "select i.layer, i.bounds, i.legend, l.fetched_at from territory.images i "
                    "left join territory.layers l on l.layer = i.layer order by i.layer"
                ).fetchall()
            except errors.UndefinedTable:
                return []
        return [
            {"layer": r[0], "bounds": list(r[1]), "legend": r[2],
             "version": r[3].isoformat() if r[3] else None}
            for r in rows
        ]  # fmt: skip

    def image(self, layer: str) -> bytes | None:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select png from territory.images where layer = %s", (layer,)
                ).fetchone()
            except errors.UndefinedTable:
                return None
        return bytes(row[0]) if row else None

    def building_tile(self, z: int, x: int, y: int) -> bytes:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(_BUILDING_TILE, {"z": z, "x": x, "y": y}).fetchone()
            except errors.UndefinedTable:
                return b""
        return bytes(row[0]) if row and row[0] else b""

    def overlaps(self, ring: Ring) -> PolygonOverlaps | None:
        closed = list(ring) if ring[0] == ring[-1] else [*ring, ring[0]]
        params = {"g": json.dumps({"type": "Polygon", "coordinates": [closed]})}
        with self._pool.connection() as conn:
            try:
                imported = conn.execute(
                    "select layer, meta ->> 'grid_kind' from territory.layers"
                ).fetchall()
            except errors.UndefinedTable:
                return None
            if not imported:
                return None
            grid_kinds = {r[0]: r[1] for r in imported if r[1]}
            grid_stats = _grid_stats(conn, params, grid_kinds) if grid_kinds else []
            has_buildings = any(r[0] == BUILDINGS_LAYER for r in imported)
            building_rows = conn.execute(_BUILDINGS, params).fetchall() if has_buildings else None
            building_points = (
                conn.execute(_BUILDING_POINTS, params).fetchall() if has_buildings else []
            )
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
            grid=grid_stats,
            buildings=(
                None
                if building_rows is None
                else [
                    BuildingStats(r[0], int(r[1]), float(r[2]), int(r[3]), float(r[4]))
                    for r in building_rows
                ]
            ),
            building_points=[
                (round(float(r[0]), 6), round(float(r[1]), 6), round(float(r[2])), bool(r[3]))
                for r in building_points
            ],
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
