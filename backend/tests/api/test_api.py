from __future__ import annotations

import json

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.queries import GetCurrentNetwork, PublishedNetwork
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap, SyntaxMap

from ..fakes import platform, territory
from ..support import METHODOLOGY_V1

LINKS = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"link_id": "1:0", "highway": "residential", "zone": "result"},
            "geometry": {"type": "LineString", "coordinates": [[-48.9, -27.1], [-48.89, -27.1]]},
        }
    ],
}


class NetworkReader:
    def __init__(self, network: PublishedNetwork | None) -> None:
        self.network = network

    def current(self) -> PublishedNetwork | None:
        return self.network


class SyntaxReader:
    def __init__(self, syntax: SyntaxMap | None) -> None:
        self.syntax = syntax

    def current(self) -> SyntaxMap | None:
        return self.syntax


class ScenarioReader:
    def list(self) -> list[dict[str, object]]:
        return []

    def get(self, name: str) -> None:
        return None


NETWORK = PublishedNetwork(
    snapshot_id="snap-1",
    manifest={"snapshot_id": "snap-1", "study_area": {"ibge_code": "4202909"}},
    links_geojson=json.dumps(LINKS).encode(),
    municipality_geojson=b'{"type":"FeatureCollection","features":[]}',
)
SYNTAX = SyntaxMap(
    analysis_id="an-1", manifest={"preliminary": True}, links_geojson=json.dumps(LINKS).encode()
)


def client(network: PublishedNetwork | None, syntax: SyntaxMap | None) -> TestClient:
    settings = Settings.from_env({"QC_METHODOLOGY_DIR": str(METHODOLOGY_V1)})
    app = create_app(
        settings,
        network_query=GetCurrentNetwork(NetworkReader(network)),
        syntax_query=GetSyntaxMap(SyntaxReader(syntax)),
        scenarios=GetScenario(ScenarioReader()),
        platform=platform(),
        territory=territory(),
    )
    return TestClient(app)


def test_empty_database_answers_503_with_instructions() -> None:
    c = client(None, None)
    assert c.get("/health").json() == {"status": "ok", "snapshot": None}
    links = c.get("/api/v1/network/links")
    assert links.status_code == 503
    assert "snapshot build" in links.json()["detail"]
    syntax = c.get("/api/v1/syntax/links")
    assert syntax.status_code == 503
    assert "analysis run" in syntax.json()["detail"]


def test_network_endpoints() -> None:
    c = client(NETWORK, None)
    assert c.get("/health").json()["snapshot"] == "snap-1"
    assert c.get("/api/v1/network/manifest").json()["study_area"]["ibge_code"] == "4202909"
    response = c.get("/api/v1/network/links")
    assert response.headers["content-type"].startswith("application/geo+json")
    assert json.loads(response.content)["features"][0]["properties"]["link_id"] == "1:0"


def test_etag_returns_304() -> None:
    c = client(NETWORK, SYNTAX)
    for path in ("/api/v1/network/links", "/api/v1/syntax/links"):
        etag = c.get(path).headers["etag"]
        assert c.get(path, headers={"If-None-Match": etag}).status_code == 304


def test_syntax_endpoints() -> None:
    c = client(NETWORK, SYNTAX)
    assert c.get("/api/v1/syntax/manifest").json()["preliminary"] is True
    assert c.get("/api/v1/syntax/links").status_code == 200


def test_unknown_scenario_is_404() -> None:
    c = client(NETWORK, SYNTAX)
    assert c.get("/api/v1/scenarios").json() == []
    assert c.get("/api/v1/scenarios/nao-existe/links").status_code == 404
