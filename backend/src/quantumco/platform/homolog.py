"""Banco de homologação: cópia da produção, sob demanda, no mesmo servidor Postgres.

Decisão de 2026-11-06 (docs/decisions.md): cópia sob demanda em vez de replicação contínua. A
homologação existe para receber ANTES da produção migrações e importações novas; com replicação
lógica isso conflita com o que chega da produção, o DDL não é replicado e um slot parado segura o
WAL no disco da produção. O banco inteiro tem ~150 MB: copiar leva segundos.

Como a cópia é feita (`quantumco db sync-homolog`):
1. cria o banco `<prod>_homolog` no mesmo servidor, se não existir;
2. apaga os schemas da aplicação na homologação e aplica EXATAMENTE as migrações que a produção
   tem (nem mais, nem menos);
3. copia os dados DENTRO do servidor via `postgres_fdw` (nada passa pela máquina de quem roda);
4. acerta as sequências e remove o servidor estrangeiro (com a credencial) ao final.

Trava: o destino precisa ter "homolog" no nome do banco, e a origem não pode ter.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from psycopg import Connection, sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from quantumco.platform.postgres import connect, dsn, migrate

log = logging.getLogger(__name__)

APP_SCHEMAS = ("road_network", "syntax_analysis", "identity", "scenarios", "territory")
_SERVER = "qc_prod"
_STAGE = "qc_prod_"  # prefixo dos schemas com as tabelas estrangeiras (temporários)


class HomologGuardError(RuntimeError):
    pass


def database_name(url: str) -> str:
    return str(conninfo_to_dict(dsn(url)).get("dbname") or "")


def is_homolog(url: str) -> bool:
    return "homolog" in database_name(url).lower()


def homolog_url_for(production_url: str) -> str:
    """Mesmo servidor e credencial, banco `<nome>_homolog`."""
    if not production_url:
        return ""
    params = conninfo_to_dict(dsn(production_url))
    params["dbname"] = f"{params.get('dbname') or 'postgres'}_homolog"
    return make_conninfo(**{k: str(v) for k, v in params.items() if v is not None})


def _check(production_url: str, homolog_url: str) -> None:
    if not production_url or not homolog_url:
        raise HomologGuardError("defina QC_DATABASE_URL (produção)")
    if is_homolog(production_url):
        raise HomologGuardError("a origem já é um banco de homologação: rode sem QC_USE_HOMOLOG")
    if not is_homolog(homolog_url):
        raise HomologGuardError(
            f"recuso escrever em {database_name(homolog_url)!r}: o destino precisa ter "
            "'homolog' no nome"
        )
    prod, homo = conninfo_to_dict(dsn(production_url)), conninfo_to_dict(dsn(homolog_url))
    if (prod.get("host"), prod.get("port")) != (homo.get("host"), homo.get("port")):
        raise HomologGuardError("a homologação precisa estar no mesmo servidor da produção")


@dataclass(frozen=True, slots=True)
class SyncReport:
    created: bool
    migrations: Sequence[str]
    tables: Sequence[tuple[str, int]]  # (schema.tabela, linhas)
    seconds: float


def ensure_database(production_url: str, homolog_url: str) -> bool:
    """Cria o banco de homologação no servidor da produção; True se criou agora."""
    _check(production_url, homolog_url)
    name = database_name(homolog_url)
    admin = conninfo_to_dict(dsn(production_url)) | {"dbname": "postgres"}
    with connect(make_conninfo(**{k: str(v) for k, v in admin.items() if v is not None})) as conn:
        conn.autocommit = True
        if conn.execute("select 1 from pg_database where datname = %s", (name,)).fetchone():
            return False
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    log.info("banco %s criado", name)
    return True


def sync(production_url: str, homolog_url: str) -> SyncReport:
    started = time.perf_counter()
    created = ensure_database(production_url, homolog_url)

    with connect(production_url) as prod:
        versions = [
            str(r[0])
            for r in prod.execute("select version from public.schema_migrations order by 1")
        ]
        row = prod.execute(
            "select current_setting('unix_socket_directories'), "
            "coalesce(inet_server_port(), 5432)::text"
        ).fetchone()
    if row is None:
        raise RuntimeError("não consegui ler a configuração do servidor de produção")
    socket_dir, port = str(row[0]), int(str(row[1]))
    prod_params = conninfo_to_dict(dsn(production_url))
    log.info("produção: %d migrações (%s)", len(versions), versions[-1] if versions else "-")

    with connect(homolog_url) as homo:
        homo.autocommit = True
        for schema in APP_SCHEMAS:
            homo.execute(sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(schema)))
        homo.execute("drop table if exists public.schema_migrations")
    applied = migrate(homolog_url, only=set(versions))
    missing = set(versions) - set(applied)
    if missing:
        raise RuntimeError(f"migrações da produção que este código não conhece: {sorted(missing)}")

    tables: list[tuple[str, int]] = []
    with connect(homolog_url) as homo:
        homo.autocommit = True
        try:
            first_socket = socket_dir.split(",", maxsplit=1)[0].strip()
            _attach_production(homo, prod_params, first_socket, port)
            with homo.transaction():
                # copia sem disparar FKs e gatilhos (a ordem das tabelas deixa de importar)
                homo.execute("set local session_replication_role = replica")
                targets = _base_tables(homo)
                homo.execute(
                    sql.SQL("truncate {}").format(
                        sql.SQL(", ").join(sql.Identifier(s, t) for s, t in targets)
                    )
                )
                for schema, table in targets:
                    t0 = time.perf_counter()
                    rows = _copy_table(homo, schema, table)
                    tables.append((f"{schema}.{table}", rows))
                    log.info("  %s.%s: %d linhas em %.1fs",
                             schema, table, rows, time.perf_counter() - t0)  # fmt: skip
                _reset_sequences(homo, targets)
        finally:
            _detach_production(homo)
    seconds = round(time.perf_counter() - started, 1)
    log.info("homologação sincronizada em %.1fs", seconds)
    return SyncReport(created, applied, tables, seconds)


def _attach_production(
    conn: Connection[Any], params: dict[str, Any], socket_dir: str, port: int
) -> None:
    conn.execute("create extension if not exists postgres_fdw")
    _detach_production(conn)
    # conexão local do próprio servidor (socket unix): os dados não saem da VPS
    conn.execute(
        sql.SQL(
            "create server {} foreign data wrapper postgres_fdw options "
            "(host {}, port {}, dbname {}, fetch_size '10000')"
        ).format(
            sql.Identifier(_SERVER),
            sql.Literal(socket_dir),
            sql.Literal(str(port)),
            sql.Literal(str(params.get("dbname"))),
        )
    )
    conn.execute(
        sql.SQL(
            "create user mapping for current_user server {} options "
            "(user {}, password {}, password_required 'false')"
        ).format(
            sql.Identifier(_SERVER),
            sql.Literal(str(params.get("user") or "postgres")),
            sql.Literal(str(params.get("password") or "")),
        )
    )
    for schema in APP_SCHEMAS:
        stage = sql.Identifier(_STAGE + schema)
        conn.execute(sql.SQL("create schema {}").format(stage))
        conn.execute(
            sql.SQL("import foreign schema {} from server {} into {}").format(
                sql.Identifier(schema), sql.Identifier(_SERVER), stage
            )
        )


def _detach_production(conn: Connection[Any]) -> None:
    """Remove as tabelas estrangeiras e o servidor (com a credencial) da homologação."""
    for schema in APP_SCHEMAS:
        conn.execute(
            sql.SQL("drop schema if exists {} cascade").format(sql.Identifier(_STAGE + schema))
        )
    conn.execute(sql.SQL("drop server if exists {} cascade").format(sql.Identifier(_SERVER)))


def _base_tables(conn: Connection[Any]) -> list[tuple[str, str]]:
    rows = conn.execute(
        "select table_schema, table_name from information_schema.tables "
        "where table_type = 'BASE TABLE' and table_schema = any(%s) order by 1, 2",
        (list(APP_SCHEMAS),),
    ).fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def _copy_table(conn: Connection[Any], schema: str, table: str) -> int:
    columns = [
        str(r[0])
        for r in conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = %s and table_name = %s and is_generated = 'NEVER' "
            "order by ordinal_position",
            (schema, table),
        ).fetchall()
    ]
    cols = sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    cursor = conn.execute(
        sql.SQL("insert into {} ({}) select {} from {}").format(
            sql.Identifier(schema, table), cols, cols, sql.Identifier(_STAGE + schema, table)
        )
    )
    return int(cursor.rowcount)


def _reset_sequences(conn: Connection[Any], targets: Sequence[tuple[str, str]]) -> None:
    for schema, table in targets:
        serial = conn.execute(
            "select column_name from information_schema.columns "
            "where table_schema = %s and table_name = %s "
            "and pg_get_serial_sequence(quote_ident(table_schema) || '.' || "
            "quote_ident(table_name), column_name) is not null",
            (schema, table),
        ).fetchall()
        for (column,) in serial:
            conn.execute(
                sql.SQL(
                    "select setval(pg_get_serial_sequence({}, {}), "
                    "coalesce((select max({}) from {}), 0) + 1, false)"
                ).format(
                    sql.Literal(f"{schema}.{table}"),
                    sql.Literal(str(column)),
                    sql.Identifier(str(column)),
                    sql.Identifier(schema, table),
                )
            )
