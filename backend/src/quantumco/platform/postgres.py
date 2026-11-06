"""Acesso ao PostGIS compartilhado pelos adaptadores de infraestrutura (nunca pelo domínio)."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Collection
from pathlib import Path
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_LOCK = 4_202_909  # advisory lock (código IBGE de Brusque, só para ser único)


def dsn(url: str) -> str:
    """Aceita o formato do SQLAlchemy (postgresql+psycopg://) e devolve o do libpq."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


# Conexões longas atravessam NAT/firewall (dev local → VPS) que derrubam TCP ocioso em silêncio:
# sem isto, o pool entrega uma conexão morta e a consulta trava até o timeout do sistema.
_CONNECTION_KWARGS: dict[str, object] = {
    "connect_timeout": 10,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 30_000,  # ms sem ACK → a conexão é dada como perdida
}


def connect(url: str) -> psycopg.Connection[tuple[object, ...]]:
    return psycopg.connect(dsn(url), **_CONNECTION_KWARGS)  # type: ignore[arg-type]


# Uma conexão parada há mais que isto é testada (1 ida e volta) antes de ser entregue; as usadas
# há pouco vão direto. Testar sempre custava uma viagem extra em todo pedido.
_CHECK_AFTER_IDLE_S = 20.0
_last_used: dict[int, float] = {}


def _mark_used(conn: psycopg.Connection[Any]) -> None:
    _last_used[id(conn)] = time.monotonic()


def _check_if_stale(conn: psycopg.Connection[Any]) -> None:
    if time.monotonic() - _last_used.get(id(conn), 0.0) > _CHECK_AFTER_IDLE_S:
        ConnectionPool.check_connection(conn)


def pool(url: str, max_size: int = 4) -> ConnectionPool:
    """Pool novo (CLI e testes). A API usa `shared_pool`, um só para todos os contextos."""
    return ConnectionPool(
        dsn(url),
        min_size=1,
        max_size=max_size,
        open=True,
        # autocommit: leitura sem BEGIN/COMMIT (menos 2 idas e voltas); escrita com mais de um
        # comando usa `conn.transaction()` explícito nos repositórios
        kwargs={**_CONNECTION_KWARGS, "autocommit": True},
        configure=_mark_used,
        reset=_mark_used,
        check=_check_if_stale,
        max_idle=120,  # fecha conexões paradas há mais de 2 min
        timeout=15,
    )


@functools.cache
def shared_pool(url: str) -> ConnectionPool:
    """O pool da aplicação: um por processo, compartilhado por todos os contextos."""
    started = time.perf_counter()
    shared = pool(url, max_size=10)
    log.info("pool do PostGIS aberto em %.0f ms", (time.perf_counter() - started) * 1000)
    return shared


def migrate(url: str, only: Collection[str] | None = None) -> list[str]:
    """Aplica as migrações SQL pendentes, em ordem, cada uma na sua transação.

    `only`: aplica só estas versões (ex.: deixar a homologação na mesma versão da produção).
    """
    applied: list[str] = []
    with connect(url) as conn:
        conn.execute("select pg_advisory_lock(%s)", (_MIGRATION_LOCK,))
        try:
            conn.execute(
                "create table if not exists public.schema_migrations "
                "(version text primary key, applied_at timestamptz not null default now())"
            )
            conn.commit()
            done = {r[0] for r in conn.execute("select version from public.schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.stem in done or (only is not None and path.stem not in only):
                    continue
                log.info("migração %s…", path.name)
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8").encode())
                    conn.execute(
                        "insert into public.schema_migrations (version) values (%s)", (path.stem,)
                    )
                applied.append(path.stem)
        finally:
            conn.execute("select pg_advisory_unlock(%s)", (_MIGRATION_LOCK,))
    return applied
