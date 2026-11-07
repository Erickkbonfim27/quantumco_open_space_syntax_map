"""Read model da rede publicada, lido do PostGIS (cache em memória por cidade e snapshot)."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from psycopg import errors
from psycopg_pool import ConnectionPool

from quantumco.road_network.application.queries import PublishedNetwork

log = logging.getLogger(__name__)

_LINKS = """
select link_id, osm_way_id, highway, zone, is_bridge, is_tunnel,
       round(length_m::numeric, 1)::float8, ST_AsGeoJSON(ST_Transform(geom, 4326), 6)
from road_network.published_links
where snapshot_id = %s
order by link_id
"""


def feature_collection(features: list[str]) -> bytes:
    return ('{"type":"FeatureCollection","features":[' + ",".join(features) + "]}").encode()


def feature(properties: dict[str, Any], geometry_json: str) -> str:
    return (
        '{"type":"Feature","properties":'
        + json.dumps(properties, ensure_ascii=False, separators=(",", ":"))
        + ',"geometry":'
        + geometry_json
        + "}"
    )


class PostgisNetworkReader:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._lock = threading.Lock()
        self._cached: dict[str, PublishedNetwork] = {}  # cidade → rede do snapshot atual

    def current(self, ibge_code: str) -> PublishedNetwork | None:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select snapshot_id, manifest from road_network.snapshots "
                    "where is_current and ibge_code = %s",
                    (ibge_code,),
                ).fetchone()
            except errors.UndefinedTable:
                return None  # migrações ainda não aplicadas: nada publicado
            if row is None:
                return None
            snapshot_id, manifest = str(row[0]), row[1]
            with self._lock:
                cached = self._cached.get(ibge_code)
                if cached is None or cached.snapshot_id != snapshot_id:
                    cached = self._cached[ibge_code] = self._load(conn, snapshot_id, manifest)
                return cached

    @staticmethod
    def _load(conn: Any, snapshot_id: str, manifest: dict[str, Any]) -> PublishedNetwork:
        started = time.perf_counter()
        features = [
            feature(
                {
                    "link_id": r[0],
                    "osm_way_id": r[1],
                    "highway": r[2],
                    "zone": r[3],
                    "is_bridge": r[4],
                    "is_tunnel": r[5],
                    "length_m": r[6],
                },
                r[7],
            )
            for r in conn.execute(_LINKS, (snapshot_id,))
        ]
        municipality = conn.execute(
            "select ST_AsGeoJSON(ST_Transform(municipality, 4326), 6), manifest->'study_area' "
            "from road_network.snapshots where snapshot_id = %s",
            (snapshot_id,),
        ).fetchone()
        network = PublishedNetwork(
            snapshot_id=snapshot_id,
            manifest=manifest,
            links_geojson=feature_collection(features),
            municipality_geojson=feature_collection(
                [feature({"ibge_code": municipality[1]["ibge_code"]}, municipality[0])]
            ),
        )
        log.info(
            "rede %s carregada do PostGIS: %d trechos em %.1fs",
            snapshot_id,
            len(features),
            time.perf_counter() - started,
        )
        return network
