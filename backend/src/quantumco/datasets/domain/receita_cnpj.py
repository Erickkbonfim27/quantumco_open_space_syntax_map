"""Cadastro Nacional da Pessoa Jurídica (Receita Federal): layout dos arquivos e o que guardamos.

Fonte oficial: compartilhamento público da Receita (Nextcloud), uma pasta por competência
(`AAAA-MM`), com ZIPs de um CSV cada: sem cabeçalho, separador `;`, aspas, texto em latin-1 e
datas `AAAAMMDD` (layout: arquivos.receitafederal.gov.br/dados/cnpj/LAYOUT_DADOS_ABERTOS_CNPJ.pdf).

LGPD: telefone, e-mail, nome fantasia (de MEI costuma ser o nome da pessoa) e sócios NÃO entram
no tratado. O endereço entra porque é o que localiza a empresa; nunca é publicado ponto a ponto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

COMPETENCIA = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")


class InvalidCompetenciaError(ValueError):
    pass


def check_competencia(value: str) -> str:
    """'2026-10' → '2026-10'; qualquer outra forma é recusada (vira nome de pasta e partição)."""
    if not COMPETENCIA.fullmatch(value):
        raise InvalidCompetenciaError(f"competência inválida: {value!r} (use AAAA-MM)")
    return value


def latest(folders: list[str]) -> str:
    """A competência mais recente entre as pastas publicadas."""
    valid = sorted(f for f in folders if COMPETENCIA.fullmatch(f))
    if not valid:
        raise InvalidCompetenciaError("nenhuma competência publicada")
    return valid[-1]


@dataclass(frozen=True, slots=True)
class Table:
    """Um tipo de arquivo da Receita e como ele vira tabela no ClickHouse."""

    name: str  # tabela no ClickHouse
    prefix: str  # nome do arquivo na Receita (Estabelecimentos0.zip, Simples.zip…)
    columns: tuple[str, ...]  # colunas do CSV, na ordem do layout oficial
    select: str  # expressão SELECT sobre input(): só o que guardamos, já convertido


# Estabelecimentos: 30 colunas no layout oficial.
ESTABELECIMENTO_COLUMNS = (
    "cnpj_basico", "cnpj_ordem", "cnpj_dv", "matriz_filial", "nome_fantasia",
    "situacao", "data_situacao", "motivo_situacao", "cidade_exterior", "pais",
    "data_inicio", "cnae_principal", "cnaes_secundarios", "tipo_logradouro", "logradouro",
    "numero", "complemento", "bairro", "cep", "uf",
    "municipio", "ddd1", "telefone1", "ddd2", "telefone2",
    "ddd_fax", "fax", "email", "situacao_especial", "data_situacao_especial",
)  # fmt: skip


def _date(column: str) -> str:
    """'20201231' → Date32 (1900–2299: há empresas abertas antes de 1970); '0'/vazio → NULL."""
    return (
        f"toDate32OrNull(concat(substring({column}, 1, 4), '-', substring({column}, 5, 2), '-', "
        f"substring({column}, 7, 2)))"
    )


def stored_columns(table: Table) -> tuple[str, ...]:
    """Colunas gravadas no ClickHouse, na ordem do SELECT (a competência vem primeiro)."""
    names = []
    for part in _split_top_level(table.select):
        alias = re.search(r"\bAS\s+(\w+)\s*$", part, re.IGNORECASE)
        names.append(alias.group(1) if alias else part.strip())
    return ("competencia", *names)


def _split_top_level(select: str) -> list[str]:
    """Separa as expressões do SELECT pelas vírgulas de fora de parênteses e aspas."""
    parts: list[str] = []
    current: list[str] = []
    depth, quoted = 0, False
    for ch in select:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quoted:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p for p in parts if p.strip()]


ESTABELECIMENTOS = Table(
    name="cnpj_estabelecimentos",
    prefix="Estabelecimentos",
    columns=ESTABELECIMENTO_COLUMNS,
    select=(
        "cnpj_basico, cnpj_ordem, cnpj_dv, toUInt8OrZero(matriz_filial) AS matriz_filial, "
        "situacao, "
        + _date("data_situacao")
        + " AS data_situacao, motivo_situacao, "
        + _date("data_inicio")
        + " AS data_inicio, cnae_principal, "
        "arrayFilter(x -> x != '', splitByChar(',', cnaes_secundarios)) AS cnaes_secundarios, "
        "tipo_logradouro, logradouro, numero, complemento, bairro, cep, uf, "
        "toUInt16OrZero(municipio) AS municipio_rf, situacao_especial"
    ),
)

SIMPLES = Table(
    name="cnpj_simples",
    prefix="Simples",
    columns=(
        "cnpj_basico",
        "opcao_simples",
        "data_opcao_simples",
        "data_exclusao_simples",
        "opcao_mei",
        "data_opcao_mei",
        "data_exclusao_mei",
    ),
    select=(
        "cnpj_basico, opcao_simples = 'S' AS simples, opcao_mei = 'S' AS mei, "
        + _date("data_opcao_mei")
        + " AS data_opcao_mei, "
        + _date("data_exclusao_mei")
        + " AS data_exclusao_mei"
    ),
)

MUNICIPIOS = Table(
    name="receita_municipios",
    prefix="Municipios",
    columns=("codigo", "nome"),
    select="toUInt16OrZero(codigo) AS codigo, nome",
)

CNAES = Table(
    name="receita_cnaes",
    prefix="Cnaes",
    columns=("codigo", "descricao"),
    select="codigo, descricao",
)

TABLES = (MUNICIPIOS, CNAES, SIMPLES, ESTABELECIMENTOS)


def table_for(file_name: str) -> Table | None:
    """'Estabelecimentos3.zip' → ESTABELECIMENTOS; Empresas/Sócios/outros → None (não usamos)."""
    stem = file_name.removesuffix(".zip")
    for table in TABLES:
        if re.fullmatch(rf"{table.prefix}\d?", stem):
            return table
    return None
