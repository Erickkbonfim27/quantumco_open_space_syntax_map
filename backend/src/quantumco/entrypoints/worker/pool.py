"""Pool de workers (2–4 processos) consumindo a fila `scenarios` no Redis.

Cada worker processa um cálculo por vez num processo filho ("work horse"): se o motor travar
ou estourar a memória, só aquele cálculo morre, o pedido é marcado como falho no banco e o
worker segue para o próximo.

No macOS o fork é inseguro (PROJ/sqlite/os_log herdados derrubam o filho com SIGSEGV): lá o
worker roda um cálculo por vez no próprio processo, sem pool nem work horse. Só para teste
local; a VPS (Linux) segue com fork.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any
from uuid import UUID

from rq import SimpleWorker, Worker
from rq.job import Job
from rq.queue import Queue
from rq.worker_pool import WorkerPool

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import connect
from quantumco.scenarios.infrastructure.redis_queue import RedisRunQueue, redis_client

log = logging.getLogger(__name__)

FORK_SAFE = sys.platform != "darwin"

KILLED = "O cálculo foi interrompido (falta de memória ou tempo esgotado). Tente com menos edições."


def _run_id(job: Job) -> UUID | None:
    try:
        return UUID(str(job.args[0]))
    except (IndexError, ValueError):
        return None


class ScenarioWorker(Worker):
    """Worker do RQ que avisa o banco quando o processo do cálculo morre sem terminar."""

    database_url: str = ""

    def handle_work_horse_killed(self, job: Job, retpid: int, ret_val: int, rusage: Any) -> None:
        super().handle_work_horse_killed(job, retpid, ret_val, rusage)  # type: ignore[no-untyped-call]
        run_id = _run_id(job)
        if run_id is None or not self.database_url:
            return
        try:
            with connect(self.database_url) as conn:
                conn.execute(
                    "update scenarios.runs set status = 'failed', error = %s, finished_at = now() "
                    "where run_id = %s and status in ('queued', 'running')",
                    (KILLED, run_id),
                )
            log.warning(
                "cálculo %s: processo morreu (retorno %s); marcado como falho", run_id, ret_val
            )
        except Exception:
            log.exception("cálculo %s: não foi possível marcar a falha no banco", run_id)


def recover(settings: Settings) -> int:
    """Pedidos 'na fila' no banco que sumiram do Redis (Redis reiniciado sem AOF) voltam à fila."""
    queue = RedisRunQueue(
        redis_client(settings.redis_url),
        timeout_s=settings.scenario_timeout_s,
        queue=settings.scenario_queue,
    )
    with connect(settings.require_database()) as conn:
        try:
            rows = conn.execute(
                "select run_id from scenarios.runs where status = 'queued' order by created_at"
            ).fetchall()
        except Exception:
            log.warning("tabela de pedidos ainda não existe; rode `quantumco db migrate`")
            return 0
    again = 0
    for row in rows:
        run_id = UUID(str(row[0]))
        if not queue.contains(run_id):
            queue.enqueue(run_id)
            again += 1
    if again:
        log.info("%d pedido(s) devolvidos à fila após reinício do Redis", again)
    return again


def start_data(settings: Settings, *, burst: bool = False) -> None:
    """Worker da fila `dados` (cargas nacionais): um processo, um job por vez, longo."""
    from quantumco.bootstrap.datasets import DATA_QUEUE  # noqa: PLC0415

    if not settings.redis_url:
        raise RuntimeError("QC_REDIS_URL não definido: o worker precisa do Redis")
    redis = redis_client(settings.redis_url)
    redis.ping()
    queue = f"{DATA_QUEUE}-homolog" if settings.use_homolog else DATA_QUEUE
    log.info("fila '%s': %d na espera; worker de dados no ar", queue,
             Queue(queue, connection=redis).count)  # fmt: skip
    worker_class = Worker if FORK_SAFE else SimpleWorker
    worker_class([queue], connection=redis).work(burst=burst, logging_level=settings.log_level)


def start(settings: Settings, workers: int, *, burst: bool = False) -> None:
    if not settings.redis_url:
        raise RuntimeError("QC_REDIS_URL não definido: o worker precisa do Redis")
    started = time.perf_counter()
    redis = redis_client(settings.redis_url)
    redis.ping()
    log.info("Redis ok em %.0f ms", (time.perf_counter() - started) * 1000)
    recover(settings)
    queue = settings.scenario_queue
    waiting = Queue(queue, connection=redis).count
    if not FORK_SAFE:
        log.info("fila '%s': %d na espera; macOS: 1 worker sem fork (teste local)", queue, waiting)
        SimpleWorker([queue], connection=redis).work(burst=burst, logging_level=settings.log_level)
        return
    log.info("fila '%s': %d na espera; subindo %d worker(s)", queue, waiting, workers)
    # importa o motor antes do fork: cada cálculo começa sem pagar o import do cityseer
    t = time.perf_counter()
    import quantumco.syntax_analysis.infrastructure.cityseer_analyzer  # noqa: F401, PLC0415

    log.info("motor carregado em %.1fs", time.perf_counter() - t)
    ScenarioWorker.database_url = settings.require_database()
    WorkerPool([queue], connection=redis, num_workers=workers, worker_class=ScenarioWorker).start(
        burst=burst, logging_level=settings.log_level
    )
