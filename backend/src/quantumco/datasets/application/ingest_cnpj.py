"""Caso de uso: carregar uma competência do CNPJ (Receita → RustFS → ClickHouse), na VPS.

Por arquivo, em sequência (no máximo um ZIP no disco temporário por vez):
1. se o bruto ainda não está no RustFS (ou está com outro tamanho), baixa da Receita e guarda;
2. se já está, pega do RustFS (não baixa da Receita de novo);
3. carrega no ClickHouse em fluxo e apaga o temporário.
A competência é recarregada do zero (idempotente): rodar de novo não duplica linhas.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from quantumco.datasets.application.ports import RawStore, ReceitaFiles, RemoteFile, Warehouse
from quantumco.datasets.domain.receita_cnpj import TABLES, check_competencia, latest, table_for

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FileReport:
    name: str
    rows: int
    size: int
    from_receita: bool  # False = reaproveitado do RustFS
    seconds: float


@dataclass(frozen=True, slots=True)
class IngestReport:
    competencia: str
    files: Sequence[FileReport]
    summary: dict[str, int]
    seconds: float


def raw_key(competencia: str, name: str) -> str:
    return f"receita/cnpj/{competencia}/{name}"


class IngestCnpj:
    def __init__(
        self,
        *,
        receita: ReceitaFiles,
        raw: RawStore,
        warehouse: Warehouse,
        scratch: Callable[[str], Path],  # caminho temporário para um nome de arquivo
    ) -> None:
        self._receita = receita
        self._raw = raw
        self._warehouse = warehouse
        self._scratch = scratch

    def __call__(self, competencia: str | None = None) -> IngestReport:
        started = time.perf_counter()
        comp = check_competencia(competencia) if competencia else latest(
            list(self._receita.competencias())
        )  # fmt: skip
        log.info("CNPJ %s: aplicando o esquema do ClickHouse…", comp)
        applied = self._warehouse.migrate()
        if applied:
            log.info("CNPJ %s: migrações do ClickHouse aplicadas: %s", comp, ", ".join(applied))
        wanted = [f for f in self._receita.files(comp) if table_for(f.name) is not None]
        order = {t.name: i for i, t in enumerate(TABLES)}
        wanted.sort(key=lambda f: (order[table_for(f.name).name], f.name))  # type: ignore[union-attr]
        total_mb = sum(f.size for f in wanted) / 1e6
        log.info("CNPJ %s: %d arquivos a carregar (%.0f MB)", comp, len(wanted), total_mb)
        for table in TABLES:
            self._warehouse.clear(table, comp)
        reports = [self._file(comp, f, i, len(wanted)) for i, f in enumerate(wanted, 1)]
        summary = self._warehouse.summary(comp)
        seconds = round(time.perf_counter() - started, 1)
        log.info("CNPJ %s: concluído em %.0fs; linhas por tabela %s", comp, seconds, summary)
        return IngestReport(comp, reports, summary, seconds)

    def _file(self, comp: str, remote: RemoteFile, i: int, n: int) -> FileReport:
        table = table_for(remote.name)
        assert table is not None
        key = raw_key(comp, remote.name)
        path = self._scratch(remote.name)
        started = time.perf_counter()
        try:
            stored = self._raw.size(key)
            from_receita = stored != remote.size
            if from_receita:
                log.info("[%d/%d] %s: baixando da Receita (%.0f MB)…",
                         i, n, remote.name, remote.size / 1e6)  # fmt: skip
                got = self._receita.download(comp, remote.name, path)
                if got != remote.size:
                    raise OSError(f"{remote.name}: baixados {got} de {remote.size} bytes")
                log.info("[%d/%d] %s: guardando o bruto no RustFS…", i, n, remote.name)
                self._raw.put(key, path)
            else:
                log.info("[%d/%d] %s: bruto já está no RustFS; usando a cópia", i, n, remote.name)
                self._raw.get(key, path)
            log.info("[%d/%d] %s: carregando em %s…", i, n, remote.name, table.name)
            t0 = time.perf_counter()
            rows = self._warehouse.load(table, comp, path)
            log.info("[%d/%d] %s: %d linhas em %.0fs",
                     i, n, remote.name, rows, time.perf_counter() - t0)  # fmt: skip
        finally:
            path.unlink(missing_ok=True)
        seconds = round(time.perf_counter() - started, 1)
        self._warehouse.log(comp, remote.name, rows, remote.size, seconds)
        return FileReport(remote.name, rows, remote.size, from_receita, seconds)
