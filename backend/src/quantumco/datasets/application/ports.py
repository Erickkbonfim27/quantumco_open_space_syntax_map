from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quantumco.datasets.domain.receita_cnpj import Table


@dataclass(frozen=True, slots=True)
class RemoteFile:
    name: str  # "Estabelecimentos0.zip"
    size: int  # bytes, como a fonte informa


class ReceitaFiles(Protocol):
    """Os arquivos publicados pela Receita (fonte oficial)."""

    def competencias(self) -> Sequence[str]: ...

    def files(self, competencia: str) -> Sequence[RemoteFile]: ...

    def download(self, competencia: str, name: str, target: Path) -> int:
        """Baixa para `target` (arquivo temporário na VPS); devolve os bytes gravados."""
        ...


class RawStore(Protocol):
    """Bruto imutável (RustFS): os ZIPs exatamente como vieram, por competência."""

    def size(self, key: str) -> int | None:
        """Tamanho guardado; None se ainda não existe."""
        ...

    def put(self, key: str, path: Path) -> None: ...

    def get(self, key: str, target: Path) -> None: ...


class Warehouse(Protocol):
    """Tratado (ClickHouse)."""

    def migrate(self) -> Sequence[str]: ...

    def clear(self, table: Table, competencia: str) -> None:
        """Apaga a competência da tabela (recarga do zero, idempotente)."""
        ...

    def load(self, table: Table, competencia: str, zip_path: Path) -> int:
        """Lê o CSV do ZIP em fluxo e insere; devolve as linhas inseridas."""
        ...

    def log(self, competencia: str, file: str, rows: int, size: int, seconds: float) -> None: ...

    def summary(self, competencia: str) -> dict[str, int]:
        """Linhas por tabela na competência (conferência no fim da carga)."""
        ...
