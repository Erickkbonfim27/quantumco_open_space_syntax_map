"""Feature flags no PostGIS (`public.feature_flags`, migração 013).

Nome ausente na tabela = desligada. Sem cache: as flags são lidas no início de cargas e comandos,
nunca num laço quente, e mudar uma flag vale na hora.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import psycopg
from psycopg_pool import ConnectionPool

_NAME = re.compile(r"^[a-z0-9_]+$")


class InvalidFlagNameError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FlagState:
    name: str
    enabled: bool
    description: str
    updated_at: datetime


def check_name(name: str) -> str:
    if not _NAME.match(name):
        raise InvalidFlagNameError(f"nome de flag inválido: {name!r} (use a-z, 0-9 e _)")
    return name


class PostgresFeatureFlags:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def is_enabled(self, name: str) -> bool:
        with self._pool.connection() as conn:
            try:
                row = conn.execute(
                    "select enabled from public.feature_flags where name = %s", (check_name(name),)
                ).fetchone()
            except psycopg.errors.UndefinedTable:
                return False  # banco sem a migração 013 (ex.: produção antes do deploy): desligada
        return bool(row and row[0])

    def set(self, name: str, enabled: bool) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "insert into public.feature_flags (name, enabled) values (%s, %s) "
                "on conflict (name) do update set enabled = excluded.enabled, updated_at = now()",
                (check_name(name), enabled),
            )

    def all(self) -> list[FlagState]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select name, enabled, description, updated_at from public.feature_flags "
                "order by name"
            ).fetchall()
        return [FlagState(str(r[0]), bool(r[1]), str(r[2]), r[3]) for r in rows]
