"""Fila de cálculo dos cenários: liga Cenários do usuário à Análise Sintática.

O contexto de cenários só conhece `ScenarioEngine`; aqui fica a tradução (camada
anticorrupção): edições em lon/lat → edições da Análise Sintática no CRS da análise.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import shared_pool
from quantumco.scenarios.application.ports import EditRejectedError
from quantumco.scenarios.application.runs import ExecuteRun, ScenarioRuns
from quantumco.scenarios.application.workspaces import Workspaces
from quantumco.scenarios.domain.network_edits import EditKind, NetworkEdit
from quantumco.scenarios.domain.run import RunQuota
from quantumco.scenarios.infrastructure.postgis_runs import PostgisRunRepository
from quantumco.scenarios.infrastructure.redis_queue import RedisRunQueue, redis_client
from quantumco.shared_kernel.clock import SystemClock
from quantumco.syntax_analysis.application.run_scenario import RunScenario
from quantumco.syntax_analysis.domain.edits import AddStreet, Edit, InvalidEditError, RemoveLink

ANALYSIS_EPSG = 31982  # SIRGAS 2000 / UTM 22S


def to_analysis_edits(edits: Sequence[NetworkEdit], epsg: int = ANALYSIS_EPSG) -> list[Edit]:
    """Remover/interditar/redesenhar tiram a via; nova via e redesenhar criam a linha."""
    from pyproj import Transformer  # noqa: PLC0415

    to_crs = Transformer.from_crs(4326, epsg, always_xy=True)
    out: list[Edit] = []
    for edit in edits:
        if edit.removes is not None:
            out.append(RemoveLink(edit.removes, closed=edit.kind == EditKind.CLOSE))
        if edit.coords is not None:
            points = tuple(
                (float(x), float(y))
                for x, y in (to_crs.transform(lon, lat) for lon, lat in edit.coords)
            )
            out.append(AddStreet(coords=points))
    return out


class SyntaxScenarioEngine:
    """`ScenarioEngine` sobre o caso de uso `RunScenario` (motor cityseer, cidade inteira)."""

    def __init__(self, run_scenario: RunScenario, forget: Callable[[str], None]) -> None:
        self._run = run_scenario
        self._forget = forget

    def run(
        self, name: str, edits: Sequence[NetworkEdit], on_stage: Callable[[str], None]
    ) -> Mapping[str, Any]:
        try:
            result, _ = self._run(name, to_analysis_edits(edits), on_stage)
        except InvalidEditError as error:
            raise EditRejectedError(_friendly(str(error))) from error
        manifest = result.manifest
        return {
            "name": name,
            "base_analysis_id": manifest["base_analysis_id"],
            "removed": len(manifest["removed"]) - len(manifest.get("closed", [])),
            "closed": len(manifest.get("closed", [])),
            "added": len(manifest["added"]),
            "snaps_m": manifest["snaps_m"],
            "pieces": manifest["pieces"],
            "engine": f"{manifest['engine']} {manifest['engine_version']}",
            "engine_seconds": manifest["engine_seconds"],
            "summary": manifest["summary_result_zone"],
            "preliminary": manifest["preliminary"],
        }

    def forget(self, name: str) -> None:
        self._forget(name)


def _friendly(message: str) -> str:
    if "da rua mais próxima" in message:
        return (
            "Uma ponta de via nova ficou longe da rede: "
            + message.split("está a ", 1)[-1]
            + ". Aproxime a ponta de uma rua existente."
        )
    if "não existe na rede base" in message:
        return "Uma via editada não existe mais na rede publicada. Remova a edição e refaça."
    return message[:1].upper() + message[1:]


def run_queue(settings: Settings) -> RedisRunQueue | None:
    if not settings.redis_url:
        return None
    return RedisRunQueue(
        redis_client(settings.redis_url),
        timeout_s=settings.scenario_timeout_s,
        queue=settings.scenario_queue,
    )


def build_runs(settings: Settings, workspaces: Workspaces) -> ScenarioRuns:
    """Para a API: pedir, acompanhar e cancelar cálculos."""
    return ScenarioRuns(
        workspaces=workspaces,
        runs=PostgisRunRepository(shared_pool(settings.require_database())),
        queue=run_queue(settings),
        clock=SystemClock(),
        quota=RunQuota(
            active_per_user=settings.scenario_active_per_user,
            daily_per_user=settings.scenario_daily_quota,
            queue_max=settings.scenario_queue_max,
        ),
    )


def build_executor(settings: Settings, worker: str) -> ExecuteRun:
    """Para o worker: processa um pedido (carrega o motor só aqui)."""
    from quantumco.bootstrap.syntax_analysis import run_scenario_use_case  # noqa: PLC0415
    from quantumco.syntax_analysis.infrastructure.postgis_scenarios import (  # noqa: PLC0415
        PostgisScenarioRepository,
    )

    database = settings.require_database()
    results = PostgisScenarioRepository(database)
    return ExecuteRun(
        runs=PostgisRunRepository(shared_pool(database)),
        engine=SyntaxScenarioEngine(run_scenario_use_case(settings), results.delete),
        clock=SystemClock(),
        worker=worker,
    )
