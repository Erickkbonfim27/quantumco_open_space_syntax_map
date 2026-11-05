"""Acesso ao PostGIS compartilhado pelos adaptadores de infraestrutura (nunca pelo domínio)."""

from __future__ import annotations

import logging
from pathlib import Path

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


def pool(url: str, max_size: int = 4) -> ConnectionPool:
    return ConnectionPool(
        dsn(url),
        min_size=1,
        max_size=max_size,
        open=True,
        kwargs=_CONNECTION_KWARGS,
        check=ConnectionPool.check_connection,  # testa antes de entregar; troca se morreu
        max_idle=120,  # fecha conexões paradas há mais de 2 min
        timeout=15,
    )


def migrate(url: str) -> list[str]:
    """Aplica as migrações SQL pendentes, em ordem, cada uma na sua transação."""
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
                if path.stem in done:
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
