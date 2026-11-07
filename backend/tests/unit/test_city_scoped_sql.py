"""Guarda contra vazamento entre cidades: toda consulta às tabelas por cidade filtra pela cidade.

Não é RLS: é uma conferência do código. Cada menção a uma tabela por cidade (ou a `is_current`)
precisa ter `ibge_code` por perto, na mesma consulta. Falso positivo raro; falso negativo é o
risco que este teste existe para pegar (uma consulta nova esquecendo a cidade).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "quantumco"
WINDOW = 420  # caracteres em volta da menção (uma consulta típica cabe nisso)

TERRITORY = re.compile(
    r"territory\.(tracts|zones|places|addresses|buildings|grid_values|grid|images|layers)\b"
)
CURRENT = re.compile(r"\bis_current\b")

FILES = {
    "territory/infrastructure/postgis_territory.py": TERRITORY,
    "road_network/infrastructure/postgis_network_reader.py": CURRENT,
    "road_network/infrastructure/postgis_snapshot_repository.py": CURRENT,
    "syntax_analysis/infrastructure/postgis_network_source.py": CURRENT,
    "syntax_analysis/infrastructure/postgis_syntax_map_reader.py": CURRENT,
    "syntax_analysis/infrastructure/postgis_analysis_repository.py": CURRENT,
    "syntax_analysis/infrastructure/postgis_scenarios.py": CURRENT,
    "syntax_analysis/infrastructure/postgis_polygon_stats.py": CURRENT,
}
# menções que não são consulta de dados de uma cidade
ALLOWED = (
    "`territory.layers.meta`",  # docstring
    "is_current = true where",  # publicação pelo id recém-gravado (a mesma cidade)
    "is_current = true where snapshot_id",
)


@pytest.mark.parametrize("relative", sorted(FILES))
def test_every_city_query_names_the_city(relative: str) -> None:
    text = (SRC / relative).read_text(encoding="utf-8")
    missing = []
    for match in FILES[relative].finditer(text):
        around = text[max(0, match.start() - WINDOW) : match.end() + WINDOW]
        line = text[text.rfind("\n", 0, match.start()) + 1 : text.find("\n", match.end())]
        if any(ok in line for ok in ALLOWED):
            continue
        if "ibge_code" not in around and "%(city)s" not in around:
            missing.append(line.strip())
    assert not missing, f"{relative}: consulta sem a cidade: {missing}"
