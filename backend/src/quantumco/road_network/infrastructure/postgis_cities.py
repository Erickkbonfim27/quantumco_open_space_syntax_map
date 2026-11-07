"""Cadastro de cidades no PostGIS (road_network.study_areas) e o catálogo que o site lê."""

from __future__ import annotations

import threading
import time
from typing import Any

from psycopg import errors
from psycopg_pool import ConnectionPool

from quantumco.platform.postgres import connect
from quantumco.road_network.application.queries import CityView
from quantumco.road_network.domain.city import City, CityStatus

_COLUMNS = "ibge_code, name, uf, slug, osm_relation_id, buffer_m, crs_epsg, status"


def _city(row: tuple[Any, ...]) -> City:
    return City(
        ibge_code=row[0],
        name=row[1],
        uf=row[2],
        slug=row[3],
        osm_relation_id=int(row[4]),
        buffer_m=float(row[5]),
        crs_epsg=int(row[6]),
        status=CityStatus(row[7]),
    )


class PostgisCityRegistry:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def get(self, ibge_code: str) -> City | None:
        with connect(self._url) as conn:
            row = conn.execute(
                f"select {_COLUMNS} from road_network.study_areas where ibge_code = %s",
                (ibge_code,),
            ).fetchone()
        return _city(row) if row else None

    def all(self) -> list[City]:
        with connect(self._url) as conn:
            rows = conn.execute(
                f"select {_COLUMNS} from road_network.study_areas order by uf, name"
            ).fetchall()
        return [_city(r) for r in rows]

    def add(self, city: City) -> None:
        with connect(self._url) as conn:
            conn.execute(
                f"insert into road_network.study_areas ({_COLUMNS}) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    city.ibge_code,
                    city.name,
                    city.uf,
                    city.slug,
                    city.osm_relation_id,
                    city.buffer_m,
                    city.crs_epsg,
                    city.status.value,
                ),
            )

    def set_status(self, ibge_code: str, status: CityStatus) -> None:
        with connect(self._url) as conn:
            conn.execute(
                "update road_network.study_areas set status = %s where ibge_code = %s",
                (status.value, ibge_code),
            )


_CATALOG = """
select c.ibge_code, c.name, c.uf, c.slug, c.status, c.crs_epsg, c.buffer_m, s.snapshot_id,
       ST_XMin(b.box), ST_YMin(b.box), ST_XMax(b.box), ST_YMax(b.box)
from road_network.study_areas c
left join road_network.snapshots s on s.ibge_code = c.ibge_code and s.is_current
left join lateral (select box2d(ST_Transform(s.municipality, 4326)) as box) b on true
order by c.uf, c.name
"""


class PostgisCityCatalog:
    """Catálogo com cache curto: a lista muda só quando uma cidade é processada."""

    TTL_S = 60.0

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool
        self._lock = threading.Lock()
        self._cached: tuple[float, list[CityView]] | None = None

    def cities(self) -> list[CityView]:
        with self._lock:
            if self._cached and time.monotonic() - self._cached[0] < self.TTL_S:
                return self._cached[1]
        with self._pool.connection() as conn:
            try:
                rows = conn.execute(_CATALOG).fetchall()
            except errors.UndefinedTable:
                return []  # migração 012 ainda não aplicada
        cities = [
            CityView(
                ibge_code=r[0],
                name=r[1],
                uf=r[2],
                slug=r[3],
                status=r[4],
                crs_epsg=int(r[5]),
                buffer_m=float(r[6]),
                snapshot_id=str(r[7]) if r[7] else None,
                bbox=(
                    (round(r[8], 6), round(r[9], 6), round(r[10], 6), round(r[11], 6))
                    if r[8] is not None
                    else None
                ),
            )
            for r in rows
        ]
        with self._lock:
            self._cached = (time.monotonic(), cities)
        return cities
