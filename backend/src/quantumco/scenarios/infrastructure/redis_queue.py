"""Fila de cálculo no Redis com RQ (Q35). O worker: `quantumco worker`."""

from __future__ import annotations

import logging
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from rq import Queue, Worker
from rq.job import Job

from quantumco.scenarios.application.ports import QueueUnavailableError

log = logging.getLogger(__name__)

QUEUE = "scenarios"
# a função do job é resolvida pelo worker a partir do nome (sem import entre as camadas)
JOB_FUNCTION = "quantumco.entrypoints.worker.jobs.execute_run"


def job_id(run_id: UUID) -> str:
    return f"run-{run_id}"


def redis_client(url: str) -> Redis:
    # a conexão só abre no primeiro comando: a API sobe mesmo com o Redis fora do ar
    return Redis.from_url(
        url, socket_connect_timeout=5, socket_timeout=15, health_check_interval=30
    )


class RedisRunQueue:
    def __init__(self, redis: Redis, *, timeout_s: int, queue: str = QUEUE) -> None:
        self._redis = redis
        self._queue = Queue(queue, connection=redis)
        self._timeout_s = timeout_s

    def enqueue(self, run_id: UUID) -> None:
        try:
            self._queue.enqueue(
                JOB_FUNCTION,
                str(run_id),
                job_id=job_id(run_id),
                job_timeout=self._timeout_s,
                result_ttl=24 * 3600,
                failure_ttl=7 * 24 * 3600,
                description=f"cenário: cálculo {run_id}",
            )
        except RedisError as error:
            log.warning("Redis indisponível ao enfileirar %s: %s", run_id, error)
            raise QueueUnavailableError(str(error)) from error

    def contains(self, run_id: UUID) -> bool:
        try:
            return bool(Job.exists(job_id(run_id), connection=self._redis))
        except RedisError:
            return True  # na dúvida, não duplica

    def workers(self) -> int | None:
        try:
            return int(Worker.count(connection=self._redis, queue=self._queue))
        except RedisError:
            return None
