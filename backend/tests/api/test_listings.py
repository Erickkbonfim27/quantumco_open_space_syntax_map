"""Rota dos imóveis à venda (ADR 0003): só com login e com a flag ligada."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.listings.application.queries import ListingsForMap
from quantumco.road_network.application.queries import GetCurrentNetwork
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap

from ..fakes import cities, platform, territory
from ..support import METHODOLOGY_V1
from .test_api import NetworkReader, ScenarioReader, SyntaxReader
from .test_platform import sign_up

HOUSE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-48.917, -27.098]},
    "properties": {"id": "2701", "property_type": "HOME", "price_brl": 650000},
}


class Flags:
    def __init__(self) -> None:
        self.enabled = False

    def is_enabled(self, name: str) -> bool:
        return self.enabled and name == "listings_glue_api"


class Reader:
    def __init__(self) -> None:
        self.asked: list[tuple[str, int]] = []

    def features(self, ibge_code: str, limit: int) -> dict[str, Any]:
        self.asked.append((ibge_code, limit))
        return {"type": "FeatureCollection", "features": [HOUSE]}


def client(flags: Flags, reader: Reader) -> TestClient:
    settings = Settings.from_env(
        {"QC_METHODOLOGY_DIR": str(METHODOLOGY_V1), "QC_COOKIE_SECURE": "false"}
    )
    app = create_app(
        settings,
        network_query=GetCurrentNetwork(NetworkReader(None)),
        syntax_query=GetSyntaxMap(SyntaxReader(None)),
        scenarios=GetScenario(ScenarioReader()),
        platform=platform(),
        territory=territory(),
        cities=cities(),
        listings=ListingsForMap(flags, reader),
    )
    return TestClient(app)


URL = "/api/v1/cities/4202909/listings"


def test_listings_need_login() -> None:
    flags, reader = Flags(), Reader()
    flags.enabled = True
    assert client(flags, reader).get(URL).status_code == 401
    assert reader.asked == []


def test_listings_follow_the_flag() -> None:
    flags, reader = Flags(), Reader()
    c = client(flags, reader)
    sign_up(c)
    off = c.get(URL)
    assert off.status_code == 404
    assert "listings_glue_api" in off.json()["detail"]
    flags.enabled = True  # a flag é lida a cada pedido: ligar vale na hora
    on = c.get(URL)
    assert on.status_code == 200
    assert on.json()["features"] == [HOUSE]
    assert on.headers["cache-control"] == "private, max-age=60"  # não vai para cache público
    assert reader.asked == [("4202909", 20_000)]


def test_listings_of_an_unknown_city_are_not_served() -> None:
    flags, reader = Flags(), Reader()
    flags.enabled = True
    c = client(flags, reader)
    sign_up(c)
    assert c.get("/api/v1/cities/9999999/listings").status_code == 404
    assert reader.asked == []
