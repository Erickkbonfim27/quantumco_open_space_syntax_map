"""Cenários no PostGIS: base para recálculo, gravação e leitura (GeoJSON com deltas)."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import numpy as np
import shapely
from psycopg import errors
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from shapely.geometry import LineString

from quantumco.platform.postgres import connect
from quantumco.syntax_analysis.application.ports import BaseAnalysis, FloatArray, ScenarioResult
from quantumco.syntax_analysis.application.queries import ScenarioMap
from quantumco.syntax_analysis.domain.segmentation import Link

log = logging.getLogger(__name__)


class PostgisBaseAnalysisSource:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def current(self, ibge_code: str) -> BaseAnalysis | None:
        with connect(self._url) as conn:
            row = conn.execute(
                "select a.analysis_id, a.snapshot_id, ST_SRID(s.municipality) "
                "from syntax_analysis.analyses a "
                "join road_network.snapshots s on s.snapshot_id = a.snapshot_id "
                "where a.is_current and a.ibge_code = %s",
                (ibge_code,),
            ).fetchone()
            if row is None:
                return None
            analysis_id, snapshot_id, srid = str(row[0]), str(row[1]), int(str(row[2]))
            rows: list[tuple[Any, ...]] = conn.execute(
                "select l.link_id, l.zone, ST_AsBinary(l.geom), m.measures "
                "from road_network.published_links l "
                "left join syntax_analysis.link_measures m "
                "  on m.analysis_id = %s and m.link_id = l.link_id "
                "where l.snapshot_id = %s order by l.link_id",
                (analysis_id, snapshot_id),
            ).fetchall()
        links: list[Link] = []
        measures: list[Mapping[str, Any]] = []
        for link_id, zone, wkb, values in rows:
            line = shapely.from_wkb(bytes(wkb))
            links.append(
                Link(
                    str(link_id),
                    tuple((float(x), float(y)) for x, y in line.coords),
                    zone == "result",
                )
            )
            measures.append(values or {})
        keys = sorted({k for m in measures for k in m if not k.startswith("c_")})
        arrays: dict[str, FloatArray] = {
            k: np.array([np.nan if m.get(k) is None else float(m[k]) for m in measures])
            for k in keys
        }
        return BaseAnalysis(
            analysis_id=analysis_id,
            snapshot_id=snapshot_id,
            links=tuple(links),
            values=arrays,
            ibge_code=ibge_code,
            crs_epsg=srid,
        )


class PostgisScenarioRepository:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def save(self, result: ScenarioResult) -> str:
        scenario_id = uuid4()
        with connect(self._url) as conn, conn.transaction():
            # reexecutar com o mesmo nome substitui o cenário anterior
            conn.execute("delete from syntax_analysis.scenarios where name = %s", (result.name,))
            conn.execute(
                "insert into syntax_analysis.scenarios (scenario_id, ibge_code, name, "
                "base_analysis_id, snapshot_id, edits, created_at, manifest) "
                "values (%s, %s, %s, %s, %s, %s, now(), %s)",
                (
                    scenario_id,
                    result.ibge_code,
                    result.name,
                    result.base_analysis_id,
                    result.snapshot_id,
                    Jsonb(list(result.edits)),
                    Jsonb(dict(result.manifest)),
                ),
            )
            with conn.cursor().copy(
                "copy syntax_analysis.scenario_link_measures (scenario_id, link_id, measures) "
                "from stdin"
            ) as copy:
                for link_id, measures in result.rows:
                    copy.write_row((scenario_id, link_id, json.dumps(dict(measures))))
            for link_id, coords in result.new_links:
                geom = shapely.set_srid(LineString(coords), result.crs_epsg)
                conn.execute(
                    "insert into syntax_analysis.scenario_new_links (scenario_id, link_id, geom) "
                    "values (%s, %s, ST_GeomFromEWKB(%s))",
                    (scenario_id, link_id, shapely.to_wkb(geom, include_srid=True)),
                )
        log.info("cenário %s gravado no PostGIS (%d trechos)", result.name, len(result.rows))
        return f"postgis:syntax_analysis.scenarios/{result.name}"

    def delete(self, name: str) -> None:
        with connect(self._url) as conn:
            conn.execute("delete from syntax_analysis.scenarios where name = %s", (name,))


_LINKS = """
select l.link_id, l.highway, l.zone, round(l.length_m::numeric, 1)::float8,
       ST_AsGeoJSON(ST_Transform(l.geom, 4326), 6), m.measures
from syntax_analysis.scenarios s
join road_network.published_links l on l.snapshot_id = s.snapshot_id
left join syntax_analysis.scenario_link_measures m
       on m.scenario_id = s.scenario_id and m.link_id = l.link_id
where s.name = %(name)s
union all
select n.link_id, 'novo', 'result', round(ST_Length(n.geom)::numeric, 1)::float8,
       ST_AsGeoJSON(ST_Transform(n.geom, 4326), 6), m.measures
from syntax_analysis.scenarios s
join syntax_analysis.scenario_new_links n on n.scenario_id = s.scenario_id
left join syntax_analysis.scenario_link_measures m
       on m.scenario_id = s.scenario_id and m.link_id = n.link_id
where s.name = %(name)s
"""


class PostgisScenarioReader:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def list(self) -> list[Mapping[str, Any]]:
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(
                    "select name, created_at, manifest, ibge_code from syntax_analysis.scenarios "
                    "order by created_at desc"
                ).fetchall()
            except errors.UndefinedTable:
                return []
        return [
            {
                "name": name,
                "ibge_code": city,
                "created_at": created.isoformat(),
                "removed": manifest.get("removed", []),
                "added": manifest.get("added", []),
                "summary": manifest.get("summary_result_zone", {}),
            }
            for name, created, manifest, city in rows
        ]

    def get(self, name: str) -> ScenarioMap | None:
        with self._pool.connection() as conn:
            try:
                head = conn.execute(
                    "select manifest from syntax_analysis.scenarios where name = %s", (name,)
                ).fetchone()
            except errors.UndefinedTable:
                return None
            if head is None:
                return None
            parts = []
            for link_id, highway, zone, length, geometry, measures in conn.execute(
                _LINKS, {"name": name}
            ):
                props = {
                    "link_id": link_id,
                    "highway": highway,
                    "zone": zone,
                    "length_m": length,
                    **(measures or {}),
                }
                parts.append(
                    '{"type":"Feature","properties":'
                    + json.dumps(props, ensure_ascii=False, separators=(",", ":"))
                    + ',"geometry":'
                    + geometry
                    + "}"
                )
        body = ('{"type":"FeatureCollection","features":[' + ",".join(parts) + "]}").encode()
        return ScenarioMap(name=name, manifest=head[0], links_geojson=body)
