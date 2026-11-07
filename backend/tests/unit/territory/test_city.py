"""O território de uma cidade: grade, recorte das fontes e arquivos do IBGE."""

from __future__ import annotations

import pytest

from quantumco.territory.domain.city import TerritoryCity
from quantumco.territory.domain.grid import BRUSQUE_GRID, grid_for_extent
from quantumco.territory.infrastructure.ibge import cnefe_url, tracts_url
from quantumco.territory.infrastructure.sgb import _inside, _params

ITAPEMA = TerritoryCity("4208302", "Itapema", "SC", (-48.690, -27.151, -48.584, -27.048))
CAMBORIU = TerritoryCity("4202008", "Balneário Camboriú", "SC", (-48.66, -27.03, -48.55, -26.95))


def test_grid_for_extent_reproduces_brusque_grid() -> None:
    # extensão dos setores de Brusque no IBGE 2022 (UTM 22S) → a grade fixa que está no banco
    assert grid_for_extent(695_614, 6_983_650, 719_200, 7_011_993) == BRUSQUE_GRID


def test_grid_for_extent_covers_the_extent_with_the_margin_on_30m_steps() -> None:
    g = grid_for_extent(730_001.5, 6_990_010.0, 742_050.0, 7_004_999.0)
    assert (g.west % 30, g.north % 30) == (0, 0)
    assert g.west <= 730_001.5 - 1000
    assert g.east >= 742_050 + 1000
    assert g.south <= 6_990_010 - 1000
    assert g.north >= 7_004_999 + 1000


def test_city_codes_and_names_for_each_source() -> None:
    assert (ITAPEMA.state_code, ITAPEMA.short_code, ITAPEMA.label) == ("42", "420830", "Itapema-SC")
    assert CAMBORIU.upper_name() == "BALNEÁRIO CAMBORIÚ"
    assert CAMBORIU.upper_name(accents=False) == "BALNEARIO CAMBORIU"
    assert ITAPEMA.contains(-48.60, -27.10, 0)
    assert not ITAPEMA.contains(-48.92, -27.10, 5000)  # Brusque fica longe
    with pytest.raises(ValueError, match="inválido"):
        TerritoryCity("42083", "x", "SC", (0, 0, 1, 1))


def test_ibge_files_come_from_the_city() -> None:
    assert tracts_url("SC").endswith("/UF/SC/SC_setores_CD2022.zip")
    listing = (
        '<a href="4202909_BRUSQUE.zip">4202909_BRUSQUE.zip</a>'
        '<a href="4208302_ITAPEMA.zip">4208302_ITAPEMA.zip</a>'
        '<a href="4208401_ITAPIRANGA.zip">x</a>'
    )
    url = cnefe_url(ITAPEMA, listing)
    assert url.endswith("/Municipio/42_SC/4208302_ITAPEMA.zip")
    with pytest.raises(FileNotFoundError):
        cnefe_url(CAMBORIU, listing)


def test_sgb_filters_by_name_and_state_and_checks_the_rectangle() -> None:
    assert _params("risco_geologico", "ITAPEMA", "SC")["CQL_FILTER"] == (
        "municipio='ITAPEMA' AND uf='SC'"
    )
    assert "''" in _params("x", "PINGO D'ÁGUA", "MG")["CQL_FILTER"]  # aspas escapadas
    near = {"type": "Point", "coordinates": [-48.62, -27.09]}
    far = {"type": "Point", "coordinates": [-48.92, -27.10]}
    assert _inside(near, ITAPEMA)
    assert not _inside(far, ITAPEMA)
    assert not _inside({}, ITAPEMA)
