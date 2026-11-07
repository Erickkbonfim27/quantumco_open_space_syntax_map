"""Lê o snapshot publicado pela Rede Viária no PostGIS (view road_network.published_links)."""

from __future__ import annotations

import shapely
from shapely.geometry import LineString

from quantumco.platform.postgres import connect
from quantumco.syntax_analysis.application.ports import AnalysisInput
from quantumco.syntax_analysis.domain.segmentation import Link


class PostgisNetworkSource:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def latest(self, ibge_code: str) -> AnalysisInput | None:
        with connect(self._url) as conn:
            row = conn.execute(
                "select snapshot_id, name, ST_SRID(municipality) from road_network.snapshots "
                "where is_current and ibge_code = %s",
                (ibge_code,),
            ).fetchone()
            if row is None:
                return None
            snapshot_id, name, srid = str(row[0]), str(row[1]), int(str(row[2]))
            rows = conn.execute(
                "select link_id, zone, ST_AsBinary(geom) from road_network.published_links "
                "where snapshot_id = %s order by link_id",
                (snapshot_id,),
            ).fetchall()
        links: list[Link] = []
        for link_id, zone, wkb in rows:
            line = shapely.from_wkb(wkb if isinstance(wkb, bytes) else bytes(memoryview(wkb)))  # type: ignore[arg-type]
            if not isinstance(line, LineString):
                raise TypeError(f"trecho {link_id} não é LineString")
            links.append(
                Link(
                    link_id=str(link_id),
                    coords=tuple((float(x), float(y)) for x, y in line.coords),
                    in_result_zone=zone == "result",
                )
            )
        return AnalysisInput(
            snapshot_id=snapshot_id,
            snapshot_name=name,
            links=tuple(links),
            ibge_code=ibge_code,
            crs_epsg=srid,
        )
