from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from quantumco.scenarios.application.runs import ExecuteRun, result_name
from quantumco.scenarios.domain.network_edits import EditKind, NetworkEdit
from quantumco.scenarios.domain.run import (
    InvalidRunTransitionError,
    RunQuota,
    RunRefusedError,
    RunStatus,
    ScenarioRun,
)

from ...fakes import Engine, RunStore
from ...support import FixedClock

NOW = datetime(2026, 11, 8, 3, 0, tzinfo=UTC)
EDITS = (NetworkEdit(EditKind.REMOVE, link_id="10"),)


def new_run() -> ScenarioRun:
    return ScenarioRun.request(workspace_id=uuid4(), owner_id=uuid4(), edits=EDITS, now=NOW)


def test_lifecycle_records_stage_timings() -> None:
    run = new_run()
    assert run.status == RunStatus.QUEUED
    assert run.stage == "queued"
    run.start(worker="w1", now=NOW + timedelta(seconds=4))
    run.enter("engine", NOW + timedelta(seconds=6))
    run.finish({"engine_seconds": 30}, NOW + timedelta(seconds=40))
    assert run.status == RunStatus.DONE
    assert run.attempts == 1
    assert [s["stage"] for s in run.stages] == ["queued", "loading", "engine"]
    assert [s["seconds"] for s in run.stages] == [4.0, 2.0, 34.0]
    with pytest.raises(InvalidRunTransitionError):
        run.start(worker="w2", now=NOW)


def test_cancel_only_while_queued() -> None:
    run = new_run()
    run.cancel(NOW)
    assert run.status == RunStatus.CANCELED
    running = new_run()
    running.start(worker="w", now=NOW)
    with pytest.raises(RunRefusedError, match="na fila"):
        running.cancel(NOW)


def test_stale_when_worker_vanishes() -> None:
    run = new_run()
    run.start(worker="w", now=NOW)
    assert not run.is_stale(NOW + timedelta(minutes=5), timedelta(minutes=25))
    assert run.is_stale(NOW + timedelta(minutes=26), timedelta(minutes=25))


def test_quota_messages() -> None:
    quota = RunQuota(active_per_user=2, daily_per_user=3, queue_max=5)
    ok = {"workspace_active": False, "active_for_user": 0, "today_for_user": 0, "queued_total": 0}
    quota.check(**ok)  # type: ignore[arg-type]
    for change, message in [
        ({"workspace_active": True}, "já está sendo calculado"),
        ({"active_for_user": 2}, "2 cálculos em andamento"),
        ({"today_for_user": 3}, "por dia"),
        ({"queued_total": 5}, "fila está cheia"),
    ]:
        with pytest.raises(RunRefusedError, match=message):
            quota.check(**{**ok, **change})  # type: ignore[arg-type]
    quota.check(**{**ok, "today_for_user": 3}, unlimited=True)  # type: ignore[arg-type]


def test_execute_run_goes_through_stages() -> None:
    store, engine = RunStore(), Engine()
    run = new_run()
    store.add(run)
    status = ExecuteRun(runs=store, engine=engine, clock=FixedClock(), worker="w1")(run.run_id)
    saved = store.get(run.run_id)
    assert status == RunStatus.DONE
    assert saved is not None
    assert [s["stage"] for s in saved.stages] == [
        "queued", "loading", "editing", "engine", "comparing", "saving",
    ]  # fmt: skip
    assert saved.result == {
        "name": result_name(run.workspace_id),
        "engine_seconds": 12.5,
        "summary": {"nain_n": {"km_up": 1.0}},
    }
    # um pedido já processado não roda de novo
    assert ExecuteRun(runs=store, engine=engine, clock=FixedClock(), worker="w")(run.run_id) == (
        RunStatus.DONE
    )
    assert len(engine.calls) == 1


def test_radii_are_validated_and_passed_to_the_engine() -> None:
    run = ScenarioRun.request(
        workspace_id=uuid4(), owner_id=uuid4(), edits=EDITS, now=NOW, radii=("800", "400")
    )
    assert run.radii == ("400", "800")
    assert not run.whole_city
    for bad in (("300",), ()):
        with pytest.raises(RunRefusedError):
            ScenarioRun.request(
                workspace_id=uuid4(), owner_id=uuid4(), edits=EDITS, now=NOW, radii=bad
            )
    store, engine = RunStore(), Engine()
    store.add(run)
    ExecuteRun(runs=store, engine=engine, clock=FixedClock(), worker="w")(run.run_id)
    assert engine.radii == [("400", "800")]


def test_execute_run_reports_rejected_edits() -> None:
    store = RunStore()
    run = new_run()
    store.add(run)
    engine = Engine(reject="Uma ponta de via nova ficou longe da rede")
    ExecuteRun(runs=store, engine=engine, clock=FixedClock(), worker="w")(run.run_id)
    saved = store.get(run.run_id)
    assert saved is not None
    assert saved.status == RunStatus.FAILED
    assert saved.error == "Uma ponta de via nova ficou longe da rede"


def test_execute_run_skips_canceled_and_vanished() -> None:
    store, engine = RunStore(), Engine()
    run = new_run()
    run.cancel(NOW)
    store.add(run)
    execute = ExecuteRun(runs=store, engine=engine, clock=FixedClock(), worker="w")
    assert execute(run.run_id) == RunStatus.CANCELED
    assert execute(uuid4()) is None
    assert engine.calls == []
