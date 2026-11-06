"""Pool de workers (2–4 processos) consumindo a fila `scenarios` no Redis.

Cada worker processa um cálculo por vez num processo filho ("work horse"): se o motor travar
ou estourar a memória, só aquele cálculo morre, o pedido é marcado como falho no banco e o
worker segue para o próximo.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from rq import Worker
from rq.job import Job
from rq.queue import Queue
from rq.worker_pool import WorkerPool

from quantumco.bootstrap.settings import Settings
from quantumco.platform.postgres import connect
from quantumco.scenarios.infrastructure.redis_queue import QUEUE, RedisRunQueue, redis_client

log = logging.getLogger(__name__)

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
    queue = RedisRunQueue(redis_client(settings.redis_url), timeout_s=settings.scenario_timeout_s)
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


def start(settings: Settings, workers: int, *, burst: bool = False) -> None:
    if not settings.redis_url:
        raise RuntimeError("QC_REDIS_URL não definido: o worker precisa do Redis")
    started = time.perf_counter()
    redis = redis_client(settings.redis_url)
    redis.ping()
    log.info("Redis ok em %.0f ms", (time.perf_counter() - started) * 1000)
    recover(settings)
    waiting = Queue(QUEUE, connection=redis).count
    log.info("fila '%s': %d na espera; subindo %d worker(s)", QUEUE, waiting, workers)
    # importa o motor antes do fork: cada cálculo começa sem pagar o import do cityseer
    t = time.perf_counter()
    import quantumco.syntax_analysis.infrastructure.cityseer_analyzer  # noqa: F401, PLC0415

    log.info("motor carregado em %.1fs", time.perf_counter() - t)
    ScenarioWorker.database_url = settings.require_database()
    WorkerPool([QUEUE], connection=redis, num_workers=workers, worker_class=ScenarioWorker).start(
        burst=burst, logging_level=settings.log_level
    )
