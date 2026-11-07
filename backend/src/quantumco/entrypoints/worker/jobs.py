"""Funções que o RQ executa (resolvidas pelo nome: `quantumco.entrypoints.worker.jobs.…`).

Rodam no "work horse", um processo filho criado pelo worker para cada cálculo: o pool de
conexões e o motor são abertos aqui, nunca no processo pai (conexões não atravessam fork).
"""

from __future__ import annotations

import functools
import os
import socket
from uuid import UUID

from rq import get_current_job

from quantumco.bootstrap.scenario_runs import build_executor
from quantumco.bootstrap.settings import Settings, load_env_file
from quantumco.scenarios.application.runs import ExecuteRun


@functools.cache
def _executor(worker: str) -> ExecuteRun:
    load_env_file()
    return build_executor(Settings.from_env(), worker)


def ingest_cnpj(competencia: str | None = None) -> dict[str, int]:
    """Carga do CNPJ (fila `dados`): roda na VPS; os arquivos da Receita não saem do servidor."""
    from quantumco.bootstrap.datasets import ingest_cnpj_use_case  # noqa: PLC0415

    load_env_file()
    report = ingest_cnpj_use_case(Settings.from_env())(competencia)
    return report.summary


def process_city(
    ibge_code: str, territory: bool = True, only: list[str] | None = None
) -> dict[str, object]:
    """Processa uma cidade (fila `dados`): rede, análise, território e publicação, na VPS."""
    from quantumco.bootstrap.city_pipeline import process_city as run  # noqa: PLC0415

    load_env_file()
    return run(Settings.from_env(), ibge_code, territory=territory, only=only)


def execute_run(run_id: str) -> str | None:
    job = get_current_job()
    worker = (job.worker_name if job else None) or f"{socket.gethostname()}:{os.getpid()}"
    status = _executor(worker)(UUID(run_id))
    return status.value if status else None
