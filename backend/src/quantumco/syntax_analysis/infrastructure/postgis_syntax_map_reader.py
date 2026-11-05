"""Read model do mapa sintático no PostGIS: trechos do snapshot da análise + medidas."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from psycopg import errors
from psycopg_pool import ConnectionPool

from quantumco.syntax_analysis.application.queries import SyntaxMap

log = logging.getLogger(__name__)

_LINKS = """
select l.link_id, l.osm_way_id, l.highway, l.zone, l.is_bridge, l.is_tunnel,
       round(l.length_m::numeric, 1)::float8,
       ST_AsGeoJSON(ST_Transform(l.geom, 4326), 6),
       m.measures
from road_network.published_links l
left join syntax_analysis.link_measures m
       on m.analysis_id = %(analysis)s and m.link_id = l.link_id
where l.snapshot_id = %(snapshot)s
order by l.link_id
"""


class PostgisSyntaxMapReader:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._lock = threading.Lock()
        self._cached: SyntaxMap | None = None

    def current(self) -> SyntaxMap | None:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select analysis_id, snapshot_id, manifest from syntax_analysis.analyses "
                    "where is_current"
                ).fetchone()
            except errors.UndefinedTable:
                return None  # migrações ainda não aplicadas: nada publicado
            if row is None:
                return None
            analysis_id, snapshot_id, manifest = str(row[0]), str(row[1]), row[2]
            with self._lock:
                if self._cached is None or self._cached.analysis_id != analysis_id:
                    self._cached = self._load(conn, analysis_id, snapshot_id, manifest)
                return self._cached

    @staticmethod
    def _load(conn: Any, analysis_id: str, snapshot_id: str, manifest: dict[str, Any]) -> SyntaxMap:
        started = time.perf_counter()
        parts: list[str] = []
        for r in conn.execute(_LINKS, {"analysis": analysis_id, "snapshot": snapshot_id}):
            props: dict[str, Any] = {
                "link_id": r[0],
                "osm_way_id": r[1],
                "highway": r[2],
                "zone": r[3],
                "is_bridge": r[4],
                "is_tunnel": r[5],
                "length_m": r[6],
                **(r[8] or {}),
            }
            parts.append(
                '{"type":"Feature","properties":'
                + json.dumps(props, ensure_ascii=False, separators=(",", ":"))
                + ',"geometry":'
                + r[7]
                + "}"
            )
        body = ('{"type":"FeatureCollection","features":[' + ",".join(parts) + "]}").encode()
        log.info(
            "mapa sintático %s carregado do PostGIS: %d trechos, %.1f MB em %.1fs",
            analysis_id,
            len(parts),
            len(body) / 1e6,
            time.perf_counter() - started,
        )
        return SyntaxMap(analysis_id=analysis_id, manifest=manifest, links_geojson=body)
