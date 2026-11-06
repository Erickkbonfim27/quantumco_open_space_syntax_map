"""Carga do CNPJ (contexto datasets): layout, SQL, WebDAV, conversão e o fluxo, sem rede."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from quantumco.datasets.application.ingest_cnpj import IngestCnpj, raw_key
from quantumco.datasets.application.ports import RemoteFile
from quantumco.datasets.domain.receita_cnpj import (
    ESTABELECIMENTO_COLUMNS,
    ESTABELECIMENTOS,
    MUNICIPIOS,
    SIMPLES,
    InvalidCompetenciaError,
    Table,
    check_competencia,
    latest,
    stored_columns,
    table_for,
)
from quantumco.datasets.infrastructure.clickhouse_warehouse import insert_sql, latin1_to_utf8
from quantumco.datasets.infrastructure.receita_webdav import parse_listing
from quantumco.platform.clickhouse import ClickHouseTarget, split_statements


def test_competencia_is_strict_and_latest_ignores_other_folders() -> None:
    assert check_competencia("2026-10") == "2026-10"
    for bad in ("2026-13", "26-10", "2026-10'; DROP TABLE x", ""):
        with pytest.raises(InvalidCompetenciaError):
            check_competencia(bad)
    assert latest(["2026-09", "cnpj.tar.gz", "2026-10", "2025-12"]) == "2026-10"


def test_only_the_files_we_use_map_to_tables() -> None:
    assert table_for("Estabelecimentos0.zip") is ESTABELECIMENTOS
    assert table_for("Estabelecimentos9.zip") is ESTABELECIMENTOS
    assert table_for("Simples.zip") is SIMPLES
    assert table_for("Municipios.zip") is MUNICIPIOS
    for ignored in ("Socios0.zip", "Empresas3.zip", "Paises.zip", "cnpj.tar.gz"):
        assert table_for(ignored) is None


def test_layout_has_30_columns_and_contacts_never_reach_the_select() -> None:
    assert len(ESTABELECIMENTO_COLUMNS) == 30
    assert ESTABELECIMENTO_COLUMNS[20] == "municipio"  # 21ª coluna do layout oficial
    stored = stored_columns(ESTABELECIMENTOS)
    for private in ("nome_fantasia", "email", "telefone1", "telefone2", "ddd1", "fax"):
        assert private not in stored
        assert private not in ESTABELECIMENTOS.select
    assert stored[0] == "competencia"
    assert "municipio_rf" in stored
    assert "cnaes_secundarios" in stored


def test_stored_columns_match_the_clickhouse_schema() -> None:
    schema = Path(__file__).parents[2] / "src/quantumco/platform/clickhouse_migrations/001_cnpj.sql"
    text = schema.read_text(encoding="utf-8")
    for table in (ESTABELECIMENTOS, SIMPLES, MUNICIPIOS):
        block = text.split(f"CREATE TABLE IF NOT EXISTS {table.name} (", 1)[1].split(") ENGINE")[0]
        declared = [line.split()[0] for line in block.splitlines() if line.strip()]
        assert list(stored_columns(table)) == declared, table.name


def test_insert_sql_reads_strings_and_validates_competencia() -> None:
    sql = insert_sql(SIMPLES, "2026-10")
    assert sql.startswith("INSERT INTO cnpj_simples (competencia, cnpj_basico, simples, mei,")
    assert "SELECT '2026-10', cnpj_basico" in sql
    assert "input('cnpj_basico String, opcao_simples String" in sql
    assert sql.endswith("FORMAT CSV")
    with pytest.raises(InvalidCompetenciaError):
        insert_sql(SIMPLES, "2026-10' OR 1=1")


def test_split_statements_drops_comments() -> None:
    script = (
        "-- topo; com ponto e vírgula\nCREATE TABLE a (x UInt8); -- fim\n\n"
        "CREATE TABLE b (y UInt8);\n"
    )
    assert split_statements(script) == ["CREATE TABLE a (x UInt8)", "CREATE TABLE b (y UInt8)"]


def test_clickhouse_url_keeps_credentials_out_of_the_base_url() -> None:
    t = ClickHouseTarget.parse("http://quantumco:s%40nha@clickhouse:8123/dados")
    assert (t.base_url, t.user, t.password, t.database) == (
        "http://clickhouse:8123", "quantumco", "s@nha", "dados",
    )  # fmt: skip
    with pytest.raises(ValueError, match="inválid"):
        ClickHouseTarget.parse("http://u:p@clickhouse:8123/dados;drop")


WEBDAV = """<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">
<d:response><d:href>/public.php/webdav/2026-10/</d:href><d:propstat><d:prop>
<d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/public.php/webdav/2026-10/Simples.zip</d:href><d:propstat><d:prop>
<d:getcontentlength>310600000</d:getcontentlength></d:prop></d:propstat></d:response>
</d:multistatus>"""


def test_webdav_listing_parses_files_and_folders() -> None:
    assert parse_listing(WEBDAV) == ["2026-10/", RemoteFile("Simples.zip", 310_600_000)]


def test_latin1_is_converted_to_utf8_without_breaking_letters() -> None:
    text = '"SÃO JOÃO";"AÇÚCAR"\n' * 300_000
    chunks = list(latin1_to_utf8(io.BytesIO(text.encode("latin-1"))))
    assert len(chunks) > 1  # passou de um pedaço de 4 MB
    assert b"".join(chunks).decode("utf-8") == text


# ------------------------------------------------------------------ fluxo da carga (dublês)


def zipped(path: Path, content: str) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("dados.csv", content.encode("latin-1"))
    return path


class Receita:
    def __init__(self, tmp: Path) -> None:
        self.downloads: list[str] = []
        self._tmp = tmp
        self._files = {"Municipios.zip": '"8055";"BRUSQUE"\n', "Socios0.zip": "x\n"}

    def competencias(self) -> Sequence[str]:
        return ["2026-09", "2026-10"]

    def files(self, competencia: str) -> Sequence[RemoteFile]:
        sizes = {
            n: zipped(self._tmp / f"src-{n}", c).stat().st_size for n, c in self._files.items()
        }
        return [RemoteFile(n, s) for n, s in sizes.items()]

    def download(self, competencia: str, name: str, target: Path) -> int:
        self.downloads.append(name)
        zipped(target, self._files[name])
        return target.stat().st_size


class Raw:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def size(self, key: str) -> int | None:
        return len(self.objects[key]) if key in self.objects else None

    def put(self, key: str, path: Path) -> None:
        self.objects[key] = path.read_bytes()

    def get(self, key: str, target: Path) -> None:
        target.write_bytes(self.objects[key])


class Warehouse:
    def __init__(self) -> None:
        self.cleared: list[str] = []
        self.loaded: list[tuple[str, str]] = []

    def migrate(self) -> Sequence[str]:
        return []

    def clear(self, table: Table, competencia: str) -> None:
        self.cleared.append(table.name)

    def load(self, table: Table, competencia: str, zip_path: Path) -> int:
        with zipfile.ZipFile(zip_path) as z:
            text = z.read(z.namelist()[0]).decode("latin-1")
        self.loaded.append((table.name, text))
        return text.count("\n")

    def log(self, competencia: str, file: str, rows: int, size: int, seconds: float) -> None:
        pass

    def summary(self, competencia: str) -> dict[str, int]:
        return {"receita_municipios": len(self.loaded)}


def test_ingest_downloads_once_then_reuses_the_raw_copy(tmp_path: Path) -> None:
    receita, raw, wh = Receita(tmp_path), Raw(), Warehouse()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    ingest = IngestCnpj(receita=receita, raw=raw, warehouse=wh, scratch=lambda n: scratch / n)

    first = ingest()  # sem competência: a mais recente
    assert first.competencia == "2026-10"
    assert receita.downloads == ["Municipios.zip"]  # Sócios nem é baixado
    assert raw_key("2026-10", "Municipios.zip") in raw.objects
    assert wh.loaded == [("receita_municipios", '"8055";"BRUSQUE"\n')]
    assert len(wh.cleared) == 4  # todas as tabelas da competência recomeçam do zero
    assert list(scratch.iterdir()) == []  # temporário apagado

    second = ingest("2026-10")
    assert receita.downloads == ["Municipios.zip"]  # não baixou de novo
    assert second.files[0].from_receita is False
