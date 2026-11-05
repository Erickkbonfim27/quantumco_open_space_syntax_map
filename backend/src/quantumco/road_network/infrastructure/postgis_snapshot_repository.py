"""Adaptador `SnapshotRepository` no PostGIS: grava e publica o snapshot numa transação só."""

from __future__ import annotations

import logging

import shapely
from psycopg.types.json import Jsonb
from shapely.geometry import LineString

from quantumco.platform.postgres import connect
from quantumco.road_network.domain.snapshot import NetworkSnapshot
from quantumco.road_network.infrastructure.manifest import build_manifest, snapshot_name

log = logging.getLogger(__name__)

_COPY_LINKS = (
    "copy road_network.links (snapshot_id, link_id, osm_way_id, from_node, to_node, highway, "
    "zone, is_bridge, is_tunnel, excluded, length_m, geom) from stdin"
)


class PostgisSnapshotRepository:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def save(self, snapshot: NetworkSnapshot, methodology_version: str) -> str:
        srid = snapshot.study_area.crs_epsg
        sid = snapshot.snapshot_id.value
        rows = [(link, False) for link in snapshot.links] + [
            (link, True) for link in snapshot.excluded_links
        ]
        with connect(self._url) as conn, conn.transaction():
            conn.execute(
                "insert into road_network.snapshots (snapshot_id, name, osm_base_timestamp, "
                "created_at, methodology_version, filter_version, manifest, municipality) "
                "values (%s, %s, %s, %s, %s, %s, %s, ST_GeomFromWKB(%s, %s))",
                (
                    sid,
                    snapshot_name(snapshot),
                    snapshot.osm_base_timestamp,
                    snapshot.created_at,
                    methodology_version,
                    snapshot.filter_version,
                    Jsonb(build_manifest(snapshot, methodology_version)),
                    shapely.to_wkb(snapshot.municipality),
                    srid,
                ),
            )
            log.info("gravando %d trechos no PostGIS (COPY)…", len(rows))
            with conn.cursor().copy(_COPY_LINKS) as copy:
                for link, excluded in rows:
                    geom = shapely.set_srid(LineString(link.coords), srid)
                    copy.write_row(
                        (
                            sid,
                            link.link_id,
                            link.osm_way_id,
                            link.from_node,
                            link.to_node,
                            link.highway,
                            link.zone.value,
                            link.is_bridge,
                            link.is_tunnel,
                            excluded,
                            link.length_m,
                            shapely.to_wkb(geom, hex=True, include_srid=True),
                        )
                    )
            # publicação atômica: só agora o snapshot vira o atual
            conn.execute("update road_network.snapshots set is_current = false where is_current")
            conn.execute(
                "update road_network.snapshots set is_current = true where snapshot_id = %s",
                (sid,),
            )
        log.info("snapshot %s publicado no PostGIS", snapshot_name(snapshot))
        return f"postgis:road_network.snapshots/{snapshot_name(snapshot)}"
