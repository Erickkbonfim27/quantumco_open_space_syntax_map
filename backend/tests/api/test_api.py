from __future__ import annotations

import json

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.queries import GetCurrentNetwork, PublishedNetwork
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap, SyntaxMap

from ..fakes import cities, platform, territory
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
    """Rede publicada só em `city` (Brusque, por padrão); guarda as cidades pedidas."""

    def __init__(self, network: PublishedNetwork | None, city: str = "4202909") -> None:
        self.network = network
        self.city = city
        self.asked: list[str] = []

    def current(self, ibge_code: str) -> PublishedNetwork | None:
        self.asked.append(ibge_code)
        return self.network if ibge_code == self.city else None


class SyntaxReader:
    def __init__(self, syntax: SyntaxMap | None, city: str = "4202909") -> None:
        self.syntax = syntax
        self.city = city
        self.asked: list[str] = []

    def current(self, ibge_code: str) -> SyntaxMap | None:
        self.asked.append(ibge_code)
        return self.syntax if ibge_code == self.city else None


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


def client(
    network: PublishedNetwork | None,
    syntax: SyntaxMap | None,
    readers: tuple[NetworkReader, SyntaxReader] | None = None,
) -> TestClient:
    settings = Settings.from_env({"QC_METHODOLOGY_DIR": str(METHODOLOGY_V1)})
    net, syn = readers or (NetworkReader(network), SyntaxReader(syntax))
    app = create_app(
        settings,
        network_query=GetCurrentNetwork(net),
        syntax_query=GetSyntaxMap(syn),
        scenarios=GetScenario(ScenarioReader()),
        platform=platform(),
        territory=territory(),
        cities=cities(),
    )
    return TestClient(app)


def test_empty_database_answers_503_with_instructions() -> None:
    c = client(None, None)
    health = c.get("/health").json()
    assert health["status"] == "ok"
    assert health["cities"] == {"4202909": "snap-brusque", "4208302": "snap-itapema"}
    links = c.get("/api/v1/cities/4202909/network/links")
    assert links.status_code == 503
    assert "cidade processar 4202909" in links.json()["detail"]
    syntax = c.get("/api/v1/cities/4202909/syntax/links")
    assert syntax.status_code == 503
    assert "analysis run" in syntax.json()["detail"]


def test_network_endpoints() -> None:
    c = client(NETWORK, None)
    manifest = c.get("/api/v1/cities/4202909/network/manifest").json()
    assert manifest["study_area"]["ibge_code"] == "4202909"
    response = c.get("/api/v1/network/links")
    assert response.headers["content-type"].startswith("application/geo+json")
    assert json.loads(response.content)["features"][0]["properties"]["link_id"] == "1:0"


def test_etag_returns_304() -> None:
    c = client(NETWORK, SYNTAX)
    for path in ("/api/v1/cities/4202909/network/links", "/api/v1/cities/4202909/syntax/links"):
        etag = c.get(path).headers["etag"]
        assert c.get(path, headers={"If-None-Match": etag}).status_code == 304


def test_syntax_endpoints() -> None:
    c = client(NETWORK, SYNTAX)
    assert c.get("/api/v1/cities/4202909/syntax/manifest").json()["preliminary"] is True
    assert c.get("/api/v1/cities/4202909/syntax/links").status_code == 200


def test_city_list_shows_only_published_cities_with_map_frame() -> None:
    c = client(None, None)
    listed = c.get("/api/v1/cities").json()
    assert [city["slug"] for city in listed] == ["brusque", "itapema"]  # Tijucas em preparo
    itapema = listed[1]
    assert itapema["ibge_code"] == "4208302"
    assert itapema["uf"] == "SC"
    assert itapema["bbox"] == [-48.69, -27.151, -48.584, -27.048]
    assert itapema["center"] == [-48.637, -27.0995]


def test_each_city_reads_only_its_own_data() -> None:
    readers = NetworkReader(NETWORK, city="4208302"), SyntaxReader(SYNTAX, city="4208302")
    c = client(None, None, readers)
    assert c.get("/api/v1/cities/4208302/network/links").status_code == 200
    assert c.get("/api/v1/cities/4208302/syntax/links").status_code == 200
    # Brusque não tem rede neste teste: a de Itapema nunca aparece no lugar dela
    assert c.get("/api/v1/cities/4202909/network/links").status_code == 503
    assert readers[0].asked == ["4208302", "4202909"]
    assert readers[1].asked == ["4208302"]


def test_unknown_or_unpublished_city_is_404_and_bad_code_is_422() -> None:
    c = client(NETWORK, SYNTAX)
    assert c.get("/api/v1/cities/4218004/network/links").status_code == 404  # em preparo
    assert c.get("/api/v1/cities/9999999/syntax/manifest").status_code == 404
    assert c.get("/api/v1/cities/brusque/network/links").status_code == 422


def test_legacy_routes_without_city_answer_brusque() -> None:
    readers = NetworkReader(NETWORK), SyntaxReader(SYNTAX)
    c = client(None, None, readers)
    assert c.get("/api/v1/network/links").status_code == 200
    assert c.get("/api/v1/syntax/manifest").status_code == 200
    assert readers[0].asked == ["4202909"]
    assert readers[1].asked == ["4202909"]


def test_unknown_scenario_is_404() -> None:
    c = client(NETWORK, SYNTAX)
    assert c.get("/api/v1/scenarios").json() == []
    assert c.get("/api/v1/scenarios/nao-existe/links").status_code == 404
