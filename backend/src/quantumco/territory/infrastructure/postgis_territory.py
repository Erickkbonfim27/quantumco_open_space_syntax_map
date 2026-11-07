"""Camadas territoriais no PostGIS (schema `territory`): gravação por COPY e recorte por área.

Tudo por cidade: gravar troca só as linhas da cidade (`ibge_code`) e toda leitura filtra por ela.
"""

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
from quantumco.territory.domain.grid import BUFFER_M, GridSpec, grid_for_extent
from quantumco.territory.domain.profile import (
    BUILDINGS_LAYER,
    BuildingStats,
    GridStat,
    TractOverlap,
    ZoneOverlap,
)
from quantumco.territory.domain.records import GridKind, GridLayer, LayerData

log = logging.getLogger(__name__)

SRID = 31982  # as colunas do schema são tipadas em UTM 22S (docs/adr/0002-multi-cidade.md)
_GEOM = (
    "ST_Multi(ST_CollectionExtract(ST_MakeValid("
    f"ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(g), 4326), {SRID})), 3))"
)


class PostgisTerritoryRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def replace(self, ibge_code: str, data: LayerData, fetched_at: datetime) -> None:
        city = ibge_code
        with self._pool.connection() as conn, conn.transaction():
            if data.tracts:
                foreign = [t.code for t in data.tracts if not t.code.startswith(city)]
                if foreign:
                    raise ValueError(f"setores de outra cidade em {city}: {foreign[:3]}")
                # ibge_code dos setores é calculado do código do setor (CD_SETOR)
                conn.execute("delete from territory.tracts where ibge_code = %s", (city,))
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
                conn.execute(
                    "delete from territory.zones where ibge_code = %s and layer = %s",
                    (city, data.layer),
                )
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
                    "insert into territory.zones "
                    "(ibge_code, layer, category, process, attrs, area_m2, geom) "
                    "select %s, layer, category, process, attrs, ST_Area(geom), geom from "
                    f"(select layer, category, process, attrs, {_GEOM} geom from stage_z) s "
                    "where not ST_IsEmpty(geom)",
                    (city,),
                )
            if data.places:
                conn.execute(
                    "delete from territory.places where ibge_code = %s and layer = %s",
                    (city, data.layer),
                )
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
                    "insert into territory.places "
                    "(ibge_code, layer, kind, name, tract_code, attrs, geom) "
                    "select %s, layer, kind, name, tract_code, attrs, "
                    f"ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), {SRID}) from stage_p",
                    (city,),
                )
            if data.addresses:
                conn.execute("delete from territory.addresses where ibge_code = %s", (city,))
                with conn.cursor().copy(
                    "copy territory.addresses (ibge_code, street, number, locality, cep, units, "
                    "search_key, lon, lat) from stdin"
                ) as copy:
                    for a in data.addresses:
                        copy.write_row(
                            (city, a.street, a.number, a.locality, a.cep, a.units, a.search_key,
                             a.lon, a.lat)
                        )  # fmt: skip
            if data.buildings:
                _replace_buildings(conn, city, data)
            meta = dict(data.meta)
            if data.grid is not None:
                meta |= _replace_grid(conn, city, data.layer, data.grid)
            conn.execute(
                "insert into territory.layers "
                "(ibge_code, layer, source, source_url, license, rows, fetched_at, meta) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s) on conflict (ibge_code, layer) do update "
                "set source = excluded.source, source_url = excluded.source_url, "
                "license = excluded.license, rows = excluded.rows, "
                "fetched_at = excluded.fetched_at, meta = excluded.meta",
                (city, data.layer, data.source, data.source_url, data.license, data.rows,
                 fetched_at, Jsonb(meta)),
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
        log.info("  %s (%s): %d %s substituídos", data.layer, city, data.rows, conn_note)

    def layers(self, ibge_code: str) -> Sequence[Mapping[str, Any]]:
        return _layers(self._pool, ibge_code)


def _replace_buildings(conn: Connection[Any], city: str, data: LayerData) -> None:
    conn.execute("delete from territory.buildings where ibge_code = %s", (city,))
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
        "(ibge_code, building_id, source, height_m, floors, class, confidence, area_m2, geom) "
        "select %s, building_id, source, height_m, floors, class, confidence, ST_Area(geom), "
        "geom from (select building_id, source, height_m, floors, class, confidence, "
        f"{_GEOM} geom from stage_b) s "
        "where not ST_IsEmpty(geom) on conflict (ibge_code, building_id) do nothing",
        (city,),
    )


# Células da grade: só as que ficam a até BUFFER_M do município (união dos setores do IBGE).
# O município é subdividido e indexado para o teste ponto-em-polígono não varrer a união inteira.
_GRID_AREA = (
    "create temp table grid_area on commit drop as "
    f"select ST_Subdivide(ST_Buffer(ST_Union(geom), {BUFFER_M}), 128) g from territory.tracts "
    "where ibge_code = %s"
)
_GRID_CELLS = f"""
insert into territory.grid (ibge_code, cell, geom)
select %(city)s, p.cell, p.geom
from (
    select r * %(ncols)s + c cell,
           ST_SetSRID(ST_MakePoint(%(west)s + (c + 0.5) * %(size)s,
                                   %(north)s - (r + 0.5) * %(size)s), {SRID}) geom
    from generate_series(0, %(nrows)s - 1) r,
         generate_series(0, %(ncols)s - 1) c
) p
where exists (select 1 from grid_area a where ST_Intersects(a.g, p.geom))
on conflict (ibge_code, cell) do nothing
"""


def _grid_spec(conn: Connection[Any], city: str) -> GridSpec:
    """A grade da cidade; na primeira vez, calculada da extensão dos setores e gravada."""
    row = conn.execute(
        "select west, north, size, ncols, nrows from territory.grids where ibge_code = %s",
        (city,),
    ).fetchone()
    if row is not None:
        return GridSpec(float(row[0]), float(row[1]), float(row[2]), int(row[3]), int(row[4]))
    extent = conn.execute(
        "select ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) "
        "from (select ST_Extent(geom) e from territory.tracts where ibge_code = %s) s",
        (city,),
    ).fetchone()
    if extent is None or extent[0] is None:
        raise RuntimeError(
            "a grade de 30 m é recortada pelo município: importe os setores antes "
            f"(`quantumco territory import --cidade {city} --only ibge-setores`)"
        )
    spec = grid_for_extent(*(float(v) for v in extent))
    conn.execute(
        "insert into territory.grids (ibge_code, west, north, size, ncols, nrows) "
        "values (%s, %s, %s, %s, %s, %s)",
        (city, spec.west, spec.north, spec.size, spec.ncols, spec.nrows),
    )
    log.info("  grade de 30 m de %s: %d × %d células", city, spec.ncols, spec.nrows)
    return spec


def _ensure_grid(conn: Connection[Any], city: str) -> None:
    exists = conn.execute(
        "select 1 from territory.grid where ibge_code = %s limit 1", (city,)
    ).fetchone()
    if exists is not None:
        return
    spec = _grid_spec(conn, city)
    started = time.perf_counter()
    conn.execute(_GRID_AREA, (city,))
    conn.execute("create index on grid_area using gist (g)")
    conn.execute(
        _GRID_CELLS,
        {"city": city, "ncols": spec.ncols, "nrows": spec.nrows, "west": spec.west,
         "north": spec.north, "size": spec.size},
    )  # fmt: skip
    (cells,) = conn.execute(  # type: ignore[misc]
        "select count(*) from territory.grid where ibge_code = %s", (city,)
    ).fetchone()
    log.info("  grade de 30 m criada: %d células em %.1fs", cells, time.perf_counter() - started)


def _replace_grid(conn: Connection[Any], city: str, layer: str, grid: GridLayer) -> dict[str, Any]:
    """Grava os valores de uma camada na grade e devolve o que vai para `territory.layers.meta`."""
    _ensure_grid(conn, city)
    conn.execute(
        "delete from territory.grid_values where ibge_code = %s and layer = %s", (city, layer)
    )
    conn.execute("create temp table stage_g (cell bigint, value real) on commit drop")
    with conn.cursor().copy("copy stage_g (cell, value) from stdin") as copy:
        for cell, value in grid.values.items():
            if math.isfinite(value):
                copy.write_row((cell, value))
    inserted = conn.execute(
        "insert into territory.grid_values (ibge_code, layer, cell, value) "
        "select %s, %s, s.cell, s.value from stage_g s "
        "join territory.grid g on g.ibge_code = %s and g.cell = s.cell",
        (city, layer, city),
    ).rowcount
    outside = len(grid.values) - inserted
    if outside:
        log.info("  %s: %d células fora do município (ou sem valor) descartadas", layer, outside)
    if grid.image is None:
        conn.execute(
            "delete from territory.images where ibge_code = %s and layer = %s", (city, layer)
        )
    else:
        img = grid.image
        conn.execute(
            "insert into territory.images (ibge_code, layer, png, bounds, legend) "
            "values (%s, %s, %s, %s, %s) on conflict (ibge_code, layer) do update "
            "set png = excluded.png, bounds = excluded.bounds, legend = excluded.legend",
            (city, layer, img.png, list(img.bounds),
             Jsonb([{"label": i.label, "color": i.color} for i in img.legend])),
        )  # fmt: skip
    return {"grid_kind": grid.kind.value, "grid_unit": grid.unit, "grid_cells": inserted}


def _layers(pool: ConnectionPool, city: str) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        try:
            rows = conn.execute(
                "select layer, source, source_url, license, rows, fetched_at from territory.layers "
                "where ibge_code = %s order by layer",
                (city,),
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
    where p.ibge_code = %(city)s and p.layer = 'cnefe' and p.kind = 'domicilio'
      and p.tract_code = t.code
) d on true
where t.ibge_code = %(city)s and ST_Intersects(t.geom, poly.g)
"""

_ZONES = f"""{_POLY}
select z.layer, z.category, z.process, z.attrs, ST_Area(ST_Intersection(z.geom, poly.g)), z.area_m2
from territory.zones z, poly
where z.ibge_code = %(city)s and ST_Intersects(z.geom, poly.g)
"""

_COUNTS = f"""{_POLY}
select p.layer, p.kind, count(*), count(*) filter (where (p.attrs ->> 'sus')::boolean)
from territory.places p, poly
where p.ibge_code = %(city)s and ST_Intersects(p.geom, poly.g)
group by 1, 2
"""

_NAMED = f"""{_POLY}
select distinct p.layer, p.kind, p.name
from territory.places p, poly
where p.ibge_code = %(city)s and p.name is not null
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
    where p.ibge_code = %(city)s and ST_Intersects(p.geom, poly.g)
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
where z.ibge_code = %(city)s and z.layer in ('risco', 'suscet_inundacao')
  and not (z.layer = 'suscet_inundacao' and z.category = 'Baixa')
  and ST_Intersects(z.geom, poly.g)
"""


# Grade de 30 m: centros de célula dentro do polígono.
_GRID_INSIDE = f"""{_POLY},
inside as (
    select g.cell from territory.grid g, poly
    where g.ibge_code = %(city)s and ST_Intersects(g.geom, poly.g)
)"""

_GRID_CONTINUOUS = f"""{_GRID_INSIDE}
select v.layer, count(*), avg(v.value), min(v.value), max(v.value),
       percentile_cont(array[0.1, 0.5, 0.9]) within group (order by v.value)
from inside i join territory.grid_values v on v.ibge_code = %(city)s and v.cell = i.cell
where v.layer = any(%(layers)s)
group by v.layer
"""

_GRID_CATEGORICAL = f"""{_GRID_INSIDE}
select v.layer, v.value, count(*)
from inside i join territory.grid_values v on v.ibge_code = %(city)s and v.cell = i.cell
where v.layer = any(%(layers)s)
group by v.layer, v.value
"""

# Contagem e altura pelo ponto interno da pegada; área pela pegada recortada.
_BUILDINGS = f"""{_POLY},
b as (
    select b.source, b.height_m, ST_Area(ST_Intersection(b.geom, poly.g)) a,
           ST_Intersects(ST_PointOnSurface(b.geom), poly.g) inside
    from territory.buildings b, poly
    where b.ibge_code = %(city)s and ST_Intersects(b.geom, poly.g)
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
    where b.ibge_code = %(city)s and b.geom && poly.g
      and ST_Intersects(ST_PointOnSurface(b.geom), poly.g)
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
    where b.ibge_code = %(city)s and b.geom && ST_Transform(
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
    + " from territory.zones where ibge_code = %(city)s and layer = 'risco'",
    "suscet_inundacao": _FEATURE.format(
        geom="ST_Transform(ST_SimplifyPreserveTopology(geom, 3), 4326)",
        props="json_build_object('categoria', category)",
    )
    + " from territory.zones where ibge_code = %(city)s and layer = 'suscet_inundacao' "
    "and category in ('Alta', 'Média')",
    "saude": _FEATURE.format(
        geom="ST_Transform(geom, 4326)",
        props="json_build_object('tipo', kind, 'nome', name, 'sus', attrs -> 'sus')",
    )
    + " from territory.places where ibge_code = %(city)s and layer = 'cnes'",
    "escolas": _FEATURE.format(
        geom="ST_Transform(geom, 4326)", props="json_build_object('nome', name)"
    )
    + " from territory.places where ibge_code = %(city)s and layer = 'cnefe' and kind = 'ensino'",
    "lugares": _FEATURE.format(
        geom="ST_Transform(geom, 4326)",
        props="json_build_object('nome', name, 'grupo', kind, 'categoria', attrs -> 'category', "
        "'fonte', attrs -> 'source')",
    )
    + " from territory.places where ibge_code = %(city)s and layer = 'lugares'",
}


class PostgisTerritoryReader:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        # as camadas só mudam no `territory import`: cache por cidade e data de importação
        self._cache: dict[tuple[str, str], tuple[str, bytes]] = {}

    def map_layer(self, ibge_code: str, name: str) -> bytes | None:
        source = {"saude": "cnes", "escolas": "cnefe"}.get(name, name)
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select fetched_at::text from territory.layers "
                    "where ibge_code = %s and layer = %s",
                    (ibge_code, source),
                ).fetchone()
            except errors.UndefinedTable:
                return None
            if row is None:
                return None
            cached = self._cache.get((ibge_code, name))
            if cached and cached[0] == row[0]:
                return cached[1]
            (text,) = conn.execute(  # type: ignore[misc]
                _FC.format(f"select {_MAP_LAYERS[name]}"), {"city": ibge_code}
            ).fetchone()
        data = str(text).encode()
        self._cache[(ibge_code, name)] = (row[0], data)
        log.info("camada %s de %s para o mapa: %.0f kB", name, ibge_code, len(data) / 1024)
        return data

    def layers(self, ibge_code: str) -> Sequence[Mapping[str, Any]]:
        return _layers(self._pool, ibge_code)

    def images(self, ibge_code: str) -> Sequence[Mapping[str, Any]]:
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(
                    "select i.layer, i.bounds, i.legend, l.fetched_at from territory.images i "
                    "left join territory.layers l "
                    "  on l.ibge_code = i.ibge_code and l.layer = i.layer "
                    "where i.ibge_code = %s order by i.layer",
                    (ibge_code,),
                ).fetchall()
            except errors.UndefinedTable:
                return []
        return [
            {"layer": r[0], "bounds": list(r[1]), "legend": r[2],
             "version": r[3].isoformat() if r[3] else None}
            for r in rows
        ]  # fmt: skip

    def image(self, ibge_code: str, layer: str) -> bytes | None:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select png from territory.images where ibge_code = %s and layer = %s",
                    (ibge_code, layer),
                ).fetchone()
            except errors.UndefinedTable:
                return None
        return bytes(row[0]) if row else None

    def building_tile(self, ibge_code: str, z: int, x: int, y: int) -> bytes:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    _BUILDING_TILE, {"city": ibge_code, "z": z, "x": x, "y": y}
                ).fetchone()
            except errors.UndefinedTable:
                return b""
        return bytes(row[0]) if row and row[0] else b""

    def overlaps(self, ibge_code: str, ring: Ring) -> PolygonOverlaps | None:
        closed = list(ring) if ring[0] == ring[-1] else [*ring, ring[0]]
        params = {
            "g": json.dumps({"type": "Polygon", "coordinates": [closed]}),
            "city": ibge_code,
        }
        with self._pool.connection() as conn:
            try:
                imported = conn.execute(
                    "select layer, meta ->> 'grid_kind' from territory.layers where ibge_code = %s",
                    (ibge_code,),
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
            imported=frozenset(str(r[0]) for r in imported),
        )


class PostgisAddressIndex:
    """Busca no índice de endereços: todas as palavras no nome do logradouro (sem acento)."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def candidates(
        self, ibge_code: str, words: Sequence[str], limit: int = 600
    ) -> list[AddressHit]:
        if not words:
            return []
        where = " and ".join(["search_key like %s"] * len(words))
        params: list[object] = [ibge_code, *(f"%{w}%" for w in words)]
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(
                    "select street, number, locality, cep, lon, lat, units "
                    f"from territory.addresses where ibge_code = %s and {where} "
                    "order by length(search_key) limit %s",
                    [*params, limit],
                ).fetchall()
            except errors.UndefinedTable:
                return []
        return [AddressHit(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]
