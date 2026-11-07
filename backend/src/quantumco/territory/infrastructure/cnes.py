"""CNES (Ministério da Saúde): estabelecimentos de saúde da cidade, com coordenada.

API de dados abertos (apidadosabertos.saude.gov.br), 20 registros por página. Guardamos só o que
o mapa precisa (nome, tipo, SUS, coordenada); telefone e e-mail ficam de fora.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from quantumco.territory.domain.city import TerritoryCity
from quantumco.territory.domain.records import LayerData, Place
from quantumco.territory.infrastructure.download import get_json

log = logging.getLogger(__name__)

API = "https://apidadosabertos.saude.gov.br/cnes/estabelecimentos"
PAGE = 20
MARGIN_M = 5000.0  # coordenada além disso do município é erro de cadastro
LICENSE = "Dados abertos do Ministério da Saúde (CNES)"

# codigo_tipo_unidade → grupo do painel
KINDS = {
    1: "atencao_basica",  # posto de saúde
    2: "atencao_basica",  # centro de saúde / UBS
    32: "atencao_basica",  # unidade móvel fluvial
    71: "atencao_basica",  # centro de apoio à saúde da família
    74: "atencao_basica",  # polo academia da saúde
    5: "hospital",  # hospital geral
    7: "hospital",  # hospital especializado
    15: "hospital",  # unidade mista
    62: "hospital",  # hospital/dia
    20: "urgencia",  # pronto-socorro geral
    21: "urgencia",  # pronto-socorro especializado
    73: "urgencia",  # pronto atendimento (UPA)
    42: "urgencia",  # unidade móvel de nível pré-hospitalar (SAMU)
    22: "consultorio",
    36: "clinica",  # clínica / centro de especialidade
    39: "diagnostico",  # unidade de apoio diagnose e terapia (SADT)
    70: "caps",  # centro de atenção psicossocial
    43: "farmacia",
}


def _float(value: object) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


class CnesSource:
    name = "cnes"

    def fetch(self, city: TerritoryCity) -> Sequence[LayerData]:
        rows: list[dict[str, object]] = []
        offset = 0
        code = city.short_code  # o DATASUS usa o código de 6 dígitos
        while True:
            page = get_json(
                API, params={"codigo_municipio": code, "limit": PAGE, "offset": offset}
            ).get("estabelecimentos", [])
            rows.extend(page)
            if offset % 200 == 0:
                log.info("  CNES: %d estabelecimentos lidos…", len(rows))
            if len(page) < PAGE:
                break
            offset += PAGE
        places, missing = [], 0
        for r in rows:
            lat = _float(r.get("latitude_estabelecimento_decimo_grau"))
            lon = _float(r.get("longitude_estabelecimento_decimo_grau"))
            if lat is None or lon is None or not city.contains(lon, lat, MARGIN_M):
                missing += 1
                continue
            unit = int(_float(r.get("codigo_tipo_unidade")) or 0)
            places.append(
                Place(
                    layer="cnes",
                    kind=KINDS.get(unit, "outro"),
                    lon=lon,
                    lat=lat,
                    name=str(r.get("nome_fantasia") or r.get("nome_razao_social") or "").title(),
                    attrs={
                        "cnes": r.get("codigo_cnes"),
                        "unit_type": unit,
                        "sus": r.get("estabelecimento_faz_atendimento_ambulatorial_sus") == "SIM",
                        "updated": r.get("data_atualizacao"),
                    },
                )
            )
        log.info(
            "  CNES: %d com coordenada em %s, %d sem coordenada (ou fora)",
            len(places),
            city.label,
            missing,
        )
        return [
            LayerData(
                layer="cnes",
                source="Ministério da Saúde · CNES (Cadastro Nacional de Estab. de Saúde)",
                source_url=f"{API}?codigo_municipio={code}",
                license=LICENSE,
                places=places,
                meta={"total": len(rows), "without_coordinates": missing},
            )
        ]
