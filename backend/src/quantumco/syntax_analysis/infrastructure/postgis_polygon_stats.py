"""Estatísticas de um polígono sobre a análise publicada (PostGIS).

N1 Território: área, perímetro (no CRS métrico da análise) e vértices.
N5 Rede viária: trechos que cruzam o polígono, km RECORTADOS pelo polígono, média de NAIN/NACH
ponderada pela extensão recortada e km por classe de cor, em cada raio.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from psycopg import errors
from psycopg_pool import ConnectionPool

SRID = 31982
CLASSES = 7

_QUERY = """
with poly as (
    select ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326), %(srid)s) g
),
analysis as (
    select analysis_id, snapshot_id from syntax_analysis.analyses where is_current
)
select ST_Length(ST_Intersection(l.geom, poly.g)) as clipped_m, m.measures
from poly, analysis
join road_network.published_links l on l.snapshot_id = analysis.snapshot_id
left join syntax_analysis.link_measures m
       on m.analysis_id = analysis.analysis_id and m.link_id = l.link_id
where l.zone = 'result' and ST_Intersects(l.geom, poly.g)
"""

_SHAPE = """
with poly as (
    select ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%(geojson)s), 4326), %(srid)s) g
)
select ST_Area(g), ST_Perimeter(g) from poly
"""


class PostgisPolygonStats:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def stats(self, ring: list[tuple[float, float]]) -> Mapping[str, Any] | None:
        closed = ring if ring[0] == ring[-1] else [*ring, ring[0]]
        params = {"geojson": json.dumps({"type": "Polygon", "coordinates": [closed]}), "srid": SRID}
        with self._pool.connection() as conn:
            try:
                if (
                    conn.execute(
                        "select 1 from syntax_analysis.analyses where is_current"
                    ).fetchone()
                    is None
                ):
                    return None
            except errors.UndefinedTable:
                return None
            area_m2, perimeter_m = conn.execute(_SHAPE, params).fetchone()  # type: ignore[misc]
            rows = conn.execute(_QUERY, params).fetchall()

        total_m = sum(float(r[0]) for r in rows)
        weighted: dict[str, float] = defaultdict(float)
        weight: dict[str, float] = defaultdict(float)
        classes_km: dict[str, list[float]] = defaultdict(lambda: [0.0] * CLASSES)
        for clipped_m, measures in rows:
            length = float(clipped_m)
            for key, value in (measures or {}).items():
                if value is None:
                    continue
                if key.startswith("c_"):
                    classes_km[key[2:]][int(value)] += length / 1000
                elif key.startswith(("nain_", "nach_")):
                    weighted[key] += float(value) * length
                    weight[key] += length

        by_radius: dict[str, dict[str, Any]] = defaultdict(dict)
        for key in sorted(weight):
            measure, radius = key.split("_", 1)
            by_radius[radius][measure] = (
                round(weighted[key] / weight[key], 4) if weight[key] else None
            )
            by_radius[radius][f"{measure}_classes_km"] = [
                round(v, 3) for v in classes_km.get(key, [0.0] * CLASSES)
            ]
        return {
            "territory": {
                "area_km2": round(float(area_m2) / 1e6, 4),
                "perimeter_km": round(float(perimeter_m) / 1000, 3),
                "vertices": len(closed) - 1,
            },
            "network": {
                "links": len(rows),
                "km": round(total_m / 1000, 3),
                "by_radius": dict(by_radius),
            },
        }
