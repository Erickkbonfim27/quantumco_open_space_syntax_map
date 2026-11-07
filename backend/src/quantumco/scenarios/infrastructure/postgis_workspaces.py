from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.scenarios.domain.network_edits import NetworkEdit
from quantumco.scenarios.domain.workspace import AreaPolygon, Measure, Status, Workspace


class PostgisWorkspaceRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def _load(self, rows: list[tuple[Any, ...]], conn: Any) -> list[Workspace]:
        if not rows:
            return []
        ids = [r[0] for r in rows]
        polygons: dict[UUID, list[AreaPolygon]] = {i: [] for i in ids}
        for workspace_id, polygon_id, code, name, geojson, created in conn.execute(
            "select workspace_id, polygon_id, code, name, ST_AsGeoJSON(geom, 7), created_at "
            "from scenarios.polygons where workspace_id = any(%s) order by code",
            (ids,),
        ):
            ring = tuple(tuple(p) for p in json.loads(geojson)["coordinates"][0])
            polygons[workspace_id].append(AreaPolygon(polygon_id, code, name, ring, created))
        return [
            Workspace(
                r[0],
                r[1],
                r[8],
                r[2],
                Measure(r[3]),
                Status(r[4]),
                r[5],
                r[6],
                polygons[r[0]],
                [NetworkEdit.from_json(e) for e in r[7] or []],
            )
            for r in rows
        ]

    _SELECT = (
        "select workspace_id, owner_id, name, measure, status, created_at, updated_at, edits, "
        "ibge_code from scenarios.workspaces "
    )

    def list_for(self, owner_id: UUID) -> list[Workspace]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                self._SELECT + "where owner_id = %s order by updated_at desc", (owner_id,)
            ).fetchall()
            return self._load(rows, conn)

    def get(self, workspace_id: UUID) -> Workspace | None:
        with self._pool.connection() as conn:
            rows = conn.execute(
                self._SELECT + "where workspace_id = %s", (workspace_id,)
            ).fetchall()
            found = self._load(rows, conn)
        return found[0] if found else None

    def save(self, workspace: Workspace) -> None:
        with self._pool.connection() as conn, conn.transaction():
            conn.execute(
                "insert into scenarios.workspaces (workspace_id, owner_id, ibge_code, name, "
                "measure, status, created_at, updated_at, edits) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "on conflict (workspace_id) do update set name = excluded.name, "
                "measure = excluded.measure, status = excluded.status, "
                "updated_at = excluded.updated_at, edits = excluded.edits",
                (
                    workspace.workspace_id,
                    workspace.owner_id,
                    workspace.ibge_code,
                    workspace.name,
                    workspace.measure.value,
                    workspace.status.value,
                    workspace.created_at,
                    workspace.updated_at,
                    Jsonb([e.to_json() for e in workspace.edits]),
                ),
            )
            conn.execute(
                "delete from scenarios.polygons where workspace_id = %s", (workspace.workspace_id,)
            )
            for polygon in workspace.polygons:
                geometry = json.dumps({"type": "Polygon", "coordinates": [list(polygon.ring)]})
                conn.execute(
                    "insert into scenarios.polygons (polygon_id, workspace_id, code, name, geom, "
                    "created_at) values (%s, %s, %s, %s, "
                    "ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s)",
                    (
                        polygon.polygon_id,
                        workspace.workspace_id,
                        polygon.code,
                        polygon.name,
                        geometry,
                        polygon.created_at,
                    ),
                )

    def delete(self, workspace_id: UUID) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "delete from scenarios.workspaces where workspace_id = %s", (workspace_id,)
            )
