"""Pedidos de cálculo no PostGIS (a fila em si fica no Redis; o estado e as etapas, aqui)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.scenarios.application.ports import RunCounts
from quantumco.scenarios.domain.network_edits import NetworkEdit
from quantumco.scenarios.domain.run import RunStatus, ScenarioRun

_COLUMNS = (
    "run_id, workspace_id, owner_id, status, stage, stages, edits, created_at, started_at, "
    "finished_at, heartbeat_at, attempts, worker, error, result, radii, ibge_code"
)


def _row(run: ScenarioRun) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "workspace_id": run.workspace_id,
        "owner_id": run.owner_id,
        "status": run.status.value,
        "stage": run.stage,
        "stages": Jsonb(run.stages),
        "edits": Jsonb([e.to_json() for e in run.edits]),
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "heartbeat_at": run.heartbeat_at,
        "attempts": run.attempts,
        "worker": run.worker,
        "error": run.error,
        "result": None if run.result is None else Jsonb(dict(run.result)),
        "radii": list(run.radii),
        "ibge_code": run.ibge_code,
    }


def _run(r: tuple[Any, ...]) -> ScenarioRun:
    return ScenarioRun(
        run_id=r[0],
        workspace_id=r[1],
        owner_id=r[2],
        status=RunStatus(r[3]),
        stage=r[4],
        stages=list(r[5] or []),
        edits=tuple(NetworkEdit.from_json(e) for e in r[6] or []),
        created_at=r[7],
        started_at=r[8],
        finished_at=r[9],
        heartbeat_at=r[10],
        attempts=r[11],
        worker=r[12],
        error=r[13],
        result=r[14],
        radii=tuple(r[15] or ()),
        ibge_code=r[16],
    )


class PostgisRunRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, run: ScenarioRun) -> None:
        names = ", ".join(f"%({c.strip()})s" for c in _COLUMNS.split(","))
        with self._pool.connection() as conn:
            conn.execute(f"insert into scenarios.runs ({_COLUMNS}) values ({names})", _row(run))

    def save(self, run: ScenarioRun) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                "update scenarios.runs set status = %(status)s, stage = %(stage)s, "
                "stages = %(stages)s, started_at = %(started_at)s, finished_at = %(finished_at)s, "
                "heartbeat_at = %(heartbeat_at)s, attempts = %(attempts)s, worker = %(worker)s, "
                "error = %(error)s, result = %(result)s where run_id = %(run_id)s",
                _row(run),
            )
            return cursor.rowcount == 1

    def _one(self, where: str, value: object) -> ScenarioRun | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                f"select {_COLUMNS} from scenarios.runs where {where} "
                "order by created_at desc limit 1",
                (value,),
            ).fetchone()
        return _run(row) if row else None

    def get(self, run_id: UUID) -> ScenarioRun | None:
        return self._one("run_id = %s", run_id)

    def latest_for(self, workspace_id: UUID) -> ScenarioRun | None:
        return self._one("workspace_id = %s", workspace_id)

    def counts(self, owner_id: UUID, since: datetime) -> RunCounts:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select "
                "  count(*) filter (where owner_id = %(o)s and status in ('queued', 'running')), "
                "  count(*) filter (where owner_id = %(o)s and created_at >= %(since)s "
                "                   and status <> 'canceled'), "
                "  count(*) filter (where status = 'queued'), "
                "  count(*) filter (where status = 'running') "
                "from scenarios.runs "
                "where status in ('queued', 'running') "
                "   or (owner_id = %(o)s and created_at >= %(since)s)",
                {"o": owner_id, "since": since},
            ).fetchone()
        assert row is not None
        return RunCounts(int(row[0]), int(row[1]), int(row[2]), int(row[3]))

    def position(self, run: ScenarioRun) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select count(*) from scenarios.runs where status = 'queued' "
                "and (created_at, run_id) < (%s, %s)",
                (run.created_at, run.run_id),
            ).fetchone()
        return int(row[0]) + 1 if row else 1

    def expected_engine_seconds(self, ibge_code: str, radii: Sequence[str]) -> float | None:
        # só cálculos da mesma cidade e com o mesmo alcance: raios locais levam segundos, a
        # cidade, minutos; e cidades de tamanhos diferentes levam tempos diferentes
        with self._pool.connection() as conn:
            row = conn.execute(
                "select avg((result->>'engine_seconds')::float8) from ("
                "  select result from scenarios.runs where status = 'done' and radii = %s "
                "  and ibge_code = %s and result ? 'engine_seconds' "
                "  order by finished_at desc limit 10) recent",
                (list(radii), ibge_code),
            ).fetchone()
        return round(float(row[0]), 1) if row and row[0] is not None else None

    def queued_ids(self) -> list[UUID]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select run_id from scenarios.runs where status = 'queued' order by created_at"
            ).fetchall()
        return [r[0] for r in rows]
