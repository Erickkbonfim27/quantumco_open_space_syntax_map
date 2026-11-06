"""IBGE Censo 2022: setores censitários (malha + agregados, renda, entorno) e CNEFE.

Uso livre citando a fonte ("Fonte: IBGE, Censo Demográfico 2022").
"""

from __future__ import annotations

import logging
import zipfile
from collections.abc import Iterator, Sequence
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon, Polygon, mapping

from quantumco.territory.domain import profile
from quantumco.territory.domain.addresses import normalize
from quantumco.territory.domain.records import Address, LayerData, Number, Place, Tract
from quantumco.territory.infrastructure.download import fetch_file

log = logging.getLogger(__name__)

MUNICIPALITY = "4202909"  # Brusque
LICENSE = "Uso livre citando a fonte: IBGE, Censo Demográfico 2022"
CENSUS = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022"
TRACTS_URL = (
    f"{CENSUS}/Agregados_por_Setores_Censitarios/malha_com_atributos/setores/shp/UF/SC/"
    "SC_setores_CD2022.zip"
)
INCOME_URL = (
    f"{CENSUS}/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/"
    "Agregados_por_setores_renda_responsavel_BR_20260508_csv.zip"
)
STREETSCAPE_URL = (
    f"{CENSUS}/Agregados_por_Setores_Censitarios_Caracteristicas_urbanisticas_do_entorno_dos_"
    "domicilios/Agregados_por_Setor_csv/Agregados_por_setores_entorno_domic%c3%adlios_BR.zip"
)
CNEFE_URL = (
    "https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/"
    f"Censo_Demografico_2022/Arquivos_CNEFE/CSV/Municipio/42_SC/{MUNICIPALITY}_BRUSQUE.zip"
)

# Variáveis do IBGE → atributos do domínio. Entorno: domicílios em faces COM o item.
BASIC = {"v0001": profile.PEOPLE, "v0003": profile.DWELLINGS, "v0007": profile.HOUSEHOLDS}
INCOME = {"V06001": profile.HEADS, "V06004": profile.INCOME_MEAN, "V06006": profile.INCOME_MEDIAN}
STREETSCAPE: dict[str, tuple[str, ...]] = {
    profile.STREETSCAPE_BASE: ("V05000",),
    "sc_heavy_traffic": ("V05001",),
    "sc_paved": ("V05006",),
    "sc_drain": ("V05009",),
    "sc_lighting": ("V05012",),
    "sc_bus_stop": ("V05015",),
    "sc_bike": ("V05018",),
    "sc_sidewalk": ("V05021",),
    "sc_obstacle": ("V05024",),
    "sc_ramp": ("V05027",),
    "sc_trees": ("V05031", "V05032", "V05033"),
    "sc_trees_5": ("V05033",),
}

# Fase B (F10): idade, alfabetização e saneamento, dos agregados por setor (dicionário de dados de
# 2026-05-20). Cada atributo nosso = soma das variáveis do IBGE listadas.
AGGREGATES = f"{CENSUS}/Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv"
DEMOGRAPHY_URL = f"{AGGREGATES}/Agregados_por_setores_demografia_BR.zip"
LITERACY_URL = f"{AGGREGATES}/Agregados_por_setores_alfabetizacao_BR.zip"
DOMICILE1_URL = f"{AGGREGATES}/Agregados_por_setores_caracteristicas_domicilio1_BR_20261021.zip"
DOMICILE2_URL = f"{AGGREGATES}/Agregados_por_setores_caracteristicas_domicilio2_BR_20250417.zip"
EXTRA: dict[str, dict[str, tuple[str, ...]]] = {
    DEMOGRAPHY_URL: {
        profile.AGE_0_14: ("V01031", "V01032", "V01033"),
        profile.AGE_15_29: ("V01034", "V01035", "V01036"),
        profile.AGE_30_59: ("V01037", "V01038", "V01039"),
        profile.AGE_60P: ("V01040", "V01041"),
    },
    LITERACY_URL: {
        # base = 15+ que sabe + que não sabe ler e escrever (mesmo par de variáveis, mesmo sigilo).
        # Somar as 13 faixas de idade (V00644–V00656) deu 104,8% na cidade: o sigilo de uma faixa
        # derrubava a base do setor e o numerador seguia contando.
        profile.POP_15P: ("V00900", "V00901"),
        profile.LITERATE_15P: ("V00900",),
    },
    DOMICILE1_URL: {profile.PERMANENT_HOUSEHOLDS: ("V00001",)},
    DOMICILE2_URL: {
        profile.WATER_NETWORK: ("V00111",),  # usa a rede geral de distribuição de água
        profile.SEWER_NETWORK: ("V00309",),  # esgoto na rede geral ou pluvial
        profile.GARBAGE_COLLECTED: ("V00397",),  # lixo coletado no domicílio
    },
}

# CNEFE: COD_ESPECIE → tipo. NV_GEO_COORD 1–3 = coordenada do endereço, da face ou da quadra;
# níveis 4+ (localidade, setor…) são grossos demais para recortar por polígono.
CNEFE_KINDS = {
    1: "domicilio",
    2: "domicilio_coletivo",
    3: "agropecuario",
    4: "ensino",
    5: "saude",
    6: "outras_finalidades",
    7: "em_construcao",
    8: "religioso",
}
CNEFE_MAX_LEVEL = 3


def _number(value: object) -> Number:
    text = str(value).strip().replace(",", ".")
    if text in {"", "X", "x", ".", "nan", "None", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _rows_for(zip_path: Path, code_column: str) -> pd.DataFrame:
    """Linhas de Brusque de um CSV nacional (lido em blocos; só texto, sem inferência).

    O nome da coluna do código muda de arquivo para arquivo (CD_SETOR, CD_setor, setor…): casa sem
    diferenciar maiúsculas. O índice sai sempre com o nome pedido.
    """
    accepted = {code_column.lower(), "setor"}
    with zipfile.ZipFile(zip_path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(name) as raw:
            parts = []
            for chunk in pd.read_csv(
                raw, sep=";", dtype=str, encoding="latin-1", chunksize=200_000
            ):
                column = next((c for c in chunk.columns if c.lower() in accepted), None)
                if column is None:
                    raise ValueError(
                        f"{zip_path.name}: sem coluna de setor ({list(chunk.columns)[:3]})"
                    )
                part = chunk[chunk[column].str.startswith(MUNICIPALITY, na=False)]
                parts.append(part.rename(columns={column: code_column}))
    found = pd.concat(parts)
    log.info("  %s: %d setores de Brusque", zip_path.name.split("-", 1)[-1], len(found))
    return found.set_index(code_column)


def _sum(frame: pd.DataFrame, code: str, columns: Sequence[str]) -> Number:
    """Soma das variáveis; None se o setor falta no arquivo ou alguma veio sigilosa ("X")."""
    if code not in frame.index:
        return None
    values = [_number(frame.at[code, c]) if c in frame.columns else None for c in columns]
    if any(v is None for v in values):
        return None
    return float(sum(v for v in values if v is not None))


def _multipolygon(geom: object) -> MultiPolygon:
    if isinstance(geom, MultiPolygon):
        return geom
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    raise ValueError(f"geometria inesperada: {type(geom).__name__}")


class CensusTractsSource:
    name = "ibge-setores"

    def __init__(self, cache_dir: Path) -> None:
        self._cache = cache_dir

    def fetch(self) -> Sequence[LayerData]:
        tracts_zip = fetch_file(TRACTS_URL, self._cache)
        income_zip = fetch_file(INCOME_URL, self._cache)
        streetscape_zip = fetch_file(STREETSCAPE_URL, self._cache)

        frame = gpd.read_file(
            f"zip://{tracts_zip}!SC_setores_CD2022.shp", where=f"CD_MUN='{MUNICIPALITY}'"
        ).to_crs(4326)
        log.info("  malha: %d setores (%s)", len(frame), frame.crs)
        income = _rows_for(income_zip, "CD_SETOR")
        streetscape = _rows_for(streetscape_zip, "CD_setor")
        extra = {url: _rows_for(fetch_file(url, self._cache), "CD_SETOR") for url in EXTRA}

        tracts: list[Tract] = []
        for row in frame.itertuples(index=False):
            code = str(row.CD_SETOR)
            attrs: dict[str, Number] = {
                ours: _number(getattr(row, theirs)) for theirs, ours in BASIC.items()
            }
            if code in income.index:
                for theirs, ours in INCOME.items():
                    attrs[ours] = _number(income.at[code, theirs])
            if code in streetscape.index:
                for ours, columns in STREETSCAPE.items():
                    values = [_number(streetscape.at[code, c]) for c in columns]
                    attrs[ours] = None if any(v is None for v in values) else sum(values)  # type: ignore[arg-type]
            for url, variables in EXTRA.items():
                for ours, columns in variables.items():
                    attrs[ours] = _sum(extra[url], code, columns)
            tracts.append(
                Tract(code=code, geometry=mapping(_multipolygon(row.geometry)), attrs=attrs)
            )
        people = sum(t.attrs.get(profile.PEOPLE) or 0 for t in tracts)
        log.info(
            "  %d setores, %d pessoas (conferência: Censo 2022 = 141.385)", len(tracts), people
        )
        return [
            LayerData(
                layer="setores",
                source="IBGE · Censo 2022 (malha de setores, agregados, renda do responsável, "
                "entorno dos domicílios, idade, alfabetização e saneamento)",
                source_url=TRACTS_URL,
                license=LICENSE,
                tracts=tracts,
                meta={
                    "people": people,
                    "income_url": INCOME_URL,
                    "streetscape_url": STREETSCAPE_URL,
                    "extra_urls": list(EXTRA),
                    "extra_variables": {
                        ours: list(cols) for v in EXTRA.values() for ours, cols in v.items()
                    },
                },
            )
        ]


class CnefeSource:
    name = "ibge-cnefe"

    def __init__(self, cache_dir: Path) -> None:
        self._cache = cache_dir

    def fetch(self) -> Sequence[LayerData]:
        path = fetch_file(CNEFE_URL, self._cache)
        places = list(self._places(path))
        log.info(
            "  CNEFE: %d endereços com coordenada fina (nível ≤ %d)", len(places), CNEFE_MAX_LEVEL
        )
        addresses = cnefe_addresses(path)
        log.info("  CNEFE: índice de busca com %d números e logradouros", len(addresses))
        source = "IBGE · CNEFE 2022 (Cadastro Nacional de Endereços para Fins Estatísticos)"
        return [
            LayerData(
                layer="cnefe", source=source, source_url=CNEFE_URL, license=LICENSE, places=places
            ),
            LayerData(
                layer="enderecos",
                source=source + " · índice de busca",
                source_url=CNEFE_URL,
                license=LICENSE,
                addresses=addresses,
            ),
        ]

    @staticmethod
    def _places(path: Path) -> Iterator[Place]:
        columns = ["COD_SETOR", "LATITUDE", "LONGITUDE", "NV_GEO_COORD", "COD_ESPECIE",
                   "DSC_ESTABELECIMENTO"]  # fmt: skip
        with zipfile.ZipFile(path) as archive:
            name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
            with archive.open(name) as raw:
                frame = pd.read_csv(raw, sep=";", dtype=str, usecols=columns, encoding="utf-8")
        skipped = 0
        for row in frame.itertuples(index=False):
            level, lat, lon = (
                _number(row.NV_GEO_COORD),
                _number(row.LATITUDE),
                _number(row.LONGITUDE),
            )
            kind = CNEFE_KINDS.get(int(_number(row.COD_ESPECIE) or 0))
            if level is None or level > CNEFE_MAX_LEVEL or lat is None or lon is None or not kind:
                skipped += 1
                continue
            label = str(row.DSC_ESTABELECIMENTO).strip()
            yield Place(
                layer="cnefe",
                kind=kind,
                lon=lon,
                lat=lat,
                # nome só de estabelecimento (escola, templo…); domicílio não tem nome
                name=label.title() if label and label != "nan" and kind != "domicilio" else None,
                tract_code=str(row.COD_SETOR)[:15],
                attrs={"level": int(level)},
            )
        log.info("  CNEFE: %d endereços sem coordenada fina ficaram de fora", skipped)


def _title(*parts: object) -> str:
    words = " ".join(str(p).strip() for p in parts if str(p).strip() not in ("", "nan"))
    small = {"de", "da", "do", "das", "dos", "e"}
    return " ".join(
        w.lower() if i and w.lower() in small else w.capitalize()
        for i, w in enumerate(words.split())
    )


def cnefe_addresses(path: Path) -> list[Address]:
    """Índice de busca: um ponto por número de logradouro (mediana) e um por logradouro."""
    columns = ["NOM_TIPO_SEGLOGR", "NOM_TITULO_SEGLOGR", "NOM_SEGLOGR", "NUM_ENDERECO", "CEP",
               "DSC_LOCALIDADE", "LATITUDE", "LONGITUDE", "NV_GEO_COORD"]  # fmt: skip
    with zipfile.ZipFile(path) as archive:
        name = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(name) as raw:
            frame = pd.read_csv(raw, sep=";", dtype=str, usecols=columns, encoding="utf-8")
    frame["lat"] = pd.to_numeric(frame["LATITUDE"], errors="coerce")
    frame["lon"] = pd.to_numeric(frame["LONGITUDE"], errors="coerce")
    level = pd.to_numeric(frame["NV_GEO_COORD"], errors="coerce")
    frame = frame[(level <= CNEFE_MAX_LEVEL) & frame["lat"].notna() & frame["lon"].notna()]
    frame = frame[frame["NOM_SEGLOGR"].notna()]
    frame["street"] = [
        _title(t, ti, n)
        for t, ti, n in zip(
            frame["NOM_TIPO_SEGLOGR"],
            frame["NOM_TITULO_SEGLOGR"],
            frame["NOM_SEGLOGR"],
            strict=True,
        )
    ]
    frame["number"] = pd.to_numeric(frame["NUM_ENDERECO"], errors="coerce")
    frame["locality"] = frame["DSC_LOCALIDADE"].fillna("").map(lambda v: _title(v) or "")
    out: list[Address] = []

    def mode(series: pd.Series) -> str | None:
        values = series.dropna()
        values = values[values != ""]
        return str(values.mode().iloc[0]) if len(values) else None

    numbered = frame[frame["number"].notna() & (frame["number"] > 0)]
    for (street, number), group in numbered.groupby(["street", "number"], sort=False):
        out.append(
            Address(str(street), int(number), mode(group["locality"]), mode(group["CEP"]),
                    float(group["lon"].median()), float(group["lat"].median()), len(group),
                    normalize(str(street)))
        )  # fmt: skip
    for street, group in frame.groupby("street", sort=False):
        out.append(
            Address(str(street), None, mode(group["locality"]), mode(group["CEP"]),
                    float(group["lon"].median()), float(group["lat"].median()), len(group),
                    normalize(str(street)))
        )  # fmt: skip
    return out
