"""Tratado no ClickHouse: o CSV do ZIP vai em fluxo (latin-1 → UTF-8) para um INSERT … input()."""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import IO

from quantumco.datasets.domain.receita_cnpj import TABLES, Table, check_competencia, stored_columns
from quantumco.platform.clickhouse import ClickHouse

log = logging.getLogger(__name__)

CHUNK = 4 << 20  # 4 MB por pedaço enviado
# limites da carga (a VPS é dividida com o PostGIS e a API): uma thread, blocos menores
LOAD_SETTINGS = {
    "format_csv_delimiter": ";",
    "max_insert_threads": 1,
    "max_threads": 1,
    "min_insert_block_size_rows": 200_000,
    "input_format_allow_errors_num": 1000,  # linhas quebradas da fonte: toleradas e contadas
    "input_format_allow_errors_ratio": 0.0001,
}


def latin1_to_utf8(raw: IO[bytes]) -> Iterator[bytes]:
    """Converte em pedaços. Em latin-1 cada byte é um caractere: o corte nunca quebra letra."""
    while chunk := raw.read(CHUNK):
        yield chunk.decode("latin-1").encode("utf-8")


def insert_sql(table: Table, competencia: str) -> str:
    comp = check_competencia(competencia)  # validada: entra como literal no SQL
    columns = ", ".join(stored_columns(table))
    structure = ", ".join(f"{c} String" for c in table.columns)
    return (
        f"INSERT INTO {table.name} ({columns}) "
        f"SELECT '{comp}', {table.select} FROM input('{structure}') FORMAT CSV"
    )


class ClickHouseWarehouse:
    def __init__(self, clickhouse: ClickHouse) -> None:
        self._ch = clickhouse

    def migrate(self) -> Sequence[str]:
        return self._ch.migrate()

    def clear(self, table: Table, competencia: str) -> None:
        comp = check_competencia(competencia)
        self._ch.command(f"ALTER TABLE {table.name} DROP PARTITION '{comp}'")

    def load(self, table: Table, competencia: str, zip_path: Path) -> int:
        with zipfile.ZipFile(zip_path) as archive:
            members = [m for m in archive.namelist() if not m.endswith("/")]
            if len(members) != 1:
                raise ValueError(f"{zip_path.name}: esperado 1 arquivo, achei {members}")
            with archive.open(members[0]) as raw:
                return self._ch.insert_stream(
                    insert_sql(table, competencia), latin1_to_utf8(raw), LOAD_SETTINGS
                )

    def log(self, competencia: str, file: str, rows: int, size: int, seconds: float) -> None:
        comp = check_competencia(competencia)
        safe = file.replace("'", "")
        self._ch.command(
            "INSERT INTO carga_log (competencia, arquivo, linhas, bytes, segundos) "
            f"VALUES ('{comp}', '{safe}', {int(rows)}, {int(size)}, {float(seconds)})"
        )

    def summary(self, competencia: str) -> dict[str, int]:
        comp = check_competencia(competencia)
        return {
            t.name: int(
                self._ch.rows(f"SELECT count() FROM {t.name} WHERE competencia = '{comp}'")[0][0]
            )
            for t in TABLES
        }
