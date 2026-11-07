"""Adaptador `MunicipalityDirectory`: API de localidades do IBGE (nome e UF pelo código)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from quantumco.road_network.application.ports import Municipality

API = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{code}"
USER_AGENT = "quantumco/1.0 (mapa sintatico aberto; +https://quantumco.com.br)"

log = logging.getLogger(__name__)


class IbgeMunicipalityDirectory:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})

    def lookup(self, ibge_code: str) -> Municipality | None:
        response = self._client.get(API.format(code=ibge_code))
        response.raise_for_status()
        data: Any = response.json()
        # a API responde [] (ou {}) para código inexistente
        if not data or not isinstance(data, dict) or "nome" not in data:
            return None
        uf = _uf_of(data)
        if uf is None:
            log.warning("IBGE %s sem UF na resposta", ibge_code)
            return None
        return Municipality(ibge_code=str(data["id"]), name=str(data["nome"]), uf=uf)


def _uf_of(data: dict[str, Any]) -> str | None:
    # o caminho até a UF mudou entre versões da API; tenta os dois
    paths = (
        ("microrregiao", "mesorregiao", "UF"),
        ("regiao-imediata", "regiao-intermediaria", "UF"),
    )
    for path in paths:
        node: Any = data
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict) and node.get("sigla"):
            return str(node["sigla"])
    return None
