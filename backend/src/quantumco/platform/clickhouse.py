"""ClickHouse pela interface HTTP (porta 8123), com httpx: sem dependência nova.

QC_CLICKHOUSE_URL = http://USUARIO:SENHA@clickhouse:8123/BANCO (host interno do Easypanel).
Usuário e senha vão em cabeçalhos (X-ClickHouse-User/Key), nunca na URL das requisições.
Migrações: arquivos `clickhouse_migrations/NNN_*.sql`, aplicados uma vez, registrados em
`schema_migrations` dentro do próprio banco.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "clickhouse_migrations"


class ClickHouseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClickHouseTarget:
    base_url: str  # http://clickhouse:8123
    user: str
    password: str
    database: str

    @classmethod
    def parse(cls, url: str) -> ClickHouseTarget:
        parsed = urlsplit(url)  # urlsplit: ";" não vira parâmetro escondido
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(
                "QC_CLICKHOUSE_URL inválida (use http://usuario:senha@host:8123/banco)"
            )
        database = parsed.path.strip("/") or "default"
        if not re.fullmatch(r"\w+", database):
            raise ValueError(f"banco do ClickHouse inválido: {database!r}")
        port = f":{parsed.port}" if parsed.port else ""
        return cls(
            base_url=f"{parsed.scheme}://{parsed.hostname}{port}",
            user=unquote(parsed.username or "default"),
            password=unquote(parsed.password or ""),
            database=database,
        )


def split_statements(script: str) -> list[str]:
    """Comandos de um arquivo .sql (a interface HTTP aceita um por requisição)."""
    without_comments = "\n".join(line.split("--", 1)[0] for line in script.splitlines())
    return [s.strip() for s in without_comments.split(";") if s.strip()]


class ClickHouse:
    def __init__(self, url: str, *, timeout: float = 60.0) -> None:
        self.target = ClickHouseTarget.parse(url)
        self._timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-ClickHouse-User": self.target.user, "X-ClickHouse-Key": self.target.password}

    def _params(self, settings: Mapping[str, object] | None) -> dict[str, str]:
        params = {"database": self.target.database}
        params |= {k: str(v) for k, v in (settings or {}).items()}
        return params

    def command(self, sql: str, settings: Mapping[str, object] | None = None) -> str:
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                self.target.base_url, params=self._params(settings),
                content=sql.encode(), headers=self._headers(),
            )  # fmt: skip
        if response.status_code != 200:
            raise ClickHouseError(response.text.strip()[:2000])
        return response.text

    def rows(self, sql: str) -> list[list[str]]:
        text = self.command(f"{sql} FORMAT TabSeparated")
        return [line.split("\t") for line in text.splitlines() if line]

    def insert_stream(
        self, sql: str, body: Iterable[bytes], settings: Mapping[str, object] | None = None
    ) -> int:
        """INSERT … FORMAT X com o corpo em fluxo; devolve as linhas gravadas (do Summary)."""
        params = self._params(settings) | {"query": sql}
        with httpx.Client(timeout=httpx.Timeout(None, connect=20)) as client:
            response = client.post(
                self.target.base_url, params=params, content=_iter(body), headers=self._headers()
            )
        if response.status_code != 200:
            raise ClickHouseError(response.text.strip()[:2000])
        summary = json.loads(response.headers.get("X-ClickHouse-Summary", "{}") or "{}")
        return int(summary.get("written_rows", 0))

    def migrate(self, directory: Path = MIGRATIONS_DIR) -> Sequence[str]:
        self.command(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version String, "
            "applied_at DateTime DEFAULT now()) ENGINE = MergeTree ORDER BY version"
        )
        done = {r[0] for r in self.rows("SELECT version FROM schema_migrations")}
        applied: list[str] = []
        for path in sorted(directory.glob("*.sql")):
            if path.stem in done:
                continue
            log.info("ClickHouse: migração %s…", path.name)
            for statement in split_statements(path.read_text(encoding="utf-8")):
                self.command(statement)
            self.command(f"INSERT INTO schema_migrations (version) VALUES ('{path.stem}')")
            applied.append(path.stem)
        return applied


def _iter(body: Iterable[bytes]) -> Iterator[bytes]:
    yield from body
