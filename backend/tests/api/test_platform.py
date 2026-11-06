from __future__ import annotations

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.queries import GetCurrentNetwork
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap

from ..fakes import platform, territory
from ..support import METHODOLOGY_V1
from .test_api import NetworkReader, ScenarioReader, SyntaxReader

RING = [[-48.92, -27.10], [-48.91, -27.10], [-48.91, -27.09], [-48.92, -27.10]]


def client() -> TestClient:
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
    )
    return TestClient(app)


def sign_up(c: TestClient, email: str = "ana@exemplo.com") -> dict[str, object]:
    r = c.post(
        "/api/v1/auth/signup",
        json={
            "name": "ana  souza",
            "email": email,
            "organization": "UFSC",
            "password": "segredo123",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["user"]


def test_signup_sets_http_only_cookie_and_me_works() -> None:
    c = client()
    user = sign_up(c)
    assert user["name"] == "ana souza"
    assert user["initials"] == "AS"
    cookie = c.cookies.get("qc_session")
    assert cookie
    assert c.get("/api/v1/me").json()["user"]["email"] == "ana@exemplo.com"


def test_signup_validation_messages() -> None:
    c = client()
    weak = c.post("/api/v1/auth/signup", json={"name": "x", "email": "a@b.com", "password": "123"})
    assert weak.status_code == 400
    assert "8 caracteres" in weak.json()["detail"]
    sign_up(c)
    again = c.post(
        "/api/v1/auth/signup",
        json={"name": "outra", "email": "ANA@exemplo.com", "password": "segredo123"},
    )
    assert again.status_code == 400
    assert "Já existe" in again.json()["detail"]


def test_login_logout() -> None:
    c = client()
    sign_up(c)
    c.post("/api/v1/auth/logout")
    assert c.get("/api/v1/me").status_code == 401
    bad = c.post("/api/v1/auth/login", json={"email": "ana@exemplo.com", "password": "errada!!"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "E-mail ou senha incorretos."
    unknown = c.post("/api/v1/auth/login", json={"email": "zz@exemplo.com", "password": "x"})
    assert unknown.json()["detail"] == "E-mail ou senha incorretos."  # não revela se existe
    ok = c.post("/api/v1/auth/login", json={"email": "ana@exemplo.com", "password": "segredo123"})
    assert ok.status_code == 200


def test_workspaces_are_private_and_hold_polygons() -> None:
    c = client()
    sign_up(c)
    assert c.get("/api/v1/workspaces").json() == []
    w = c.post("/api/v1/workspaces", json={"name": "Centro 2030", "measure": "nach"}).json()
    assert w["status"] == "rascunho"
    p = c.post(f"/api/v1/workspaces/{w['id']}/polygons", json={"coordinates": RING}).json()
    assert p["code"] == "P-01"
    full = c.get(f"/api/v1/workspaces/{w['id']}").json()
    assert full["polygons"] == 1
    assert full["features"][0]["properties"]["code"] == "P-01"

    # outro usuário não enxerga o cenário
    other = client()
    sign_up(other, "bia@exemplo.com")
    assert other.get(f"/api/v1/workspaces/{w['id']}").status_code == 404

    renamed = c.patch(f"/api/v1/workspaces/{w['id']}", json={"status": "em_analise"}).json()
    assert renamed["status"] == "em_analise"
    assert c.delete(f"/api/v1/workspaces/{w['id']}/polygons/{p['id']}").status_code == 204
    assert c.delete(f"/api/v1/workspaces/{w['id']}").status_code == 204
    assert c.get("/api/v1/workspaces").json() == []


def test_invalid_polygon_and_auth_required() -> None:
    c = client()
    assert c.get("/api/v1/workspaces").status_code == 401
    sign_up(c)
    w = c.post("/api/v1/workspaces", json={"name": "x"}).json()
    far = [[0, 0], [1, 0], [1, 1], [0, 0]]
    r = c.post(f"/api/v1/workspaces/{w['id']}/polygons", json={"coordinates": far})
    assert r.status_code == 400
    assert "Brusque" in r.json()["detail"]


def test_polygon_stats_is_public() -> None:
    c = client()
    r = c.post("/api/v1/syntax/polygon-stats", json={"coordinates": RING})
    assert r.status_code == 200
    assert r.json()["territory"]["vertices"] == 4


def test_territory_profile_is_public() -> None:
    c = client()
    r = c.post("/api/v1/territory/polygon-profile", json={"coordinates": RING})
    assert r.status_code == 200
    body = r.json()
    # metade dos domicílios do setor está dentro → metade da população (não 90% pela área)
    assert body["population"]["people"] == 250
    assert body["risk"]["sectors"] == 1
    assert body["health"]["public_units"] == ["Hospital Azambuja"]
    assert body["layers"][0]["layer"] == "setores"
    assert c.get("/api/v1/territory/layers").status_code == 200


def test_territory_map_layers() -> None:
    c = client()
    r = c.get("/api/v1/territory/map/risco")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/geo+json")
    assert c.get("/api/v1/territory/map/lotes").status_code == 404


def test_territory_profile_has_phase_b_blocks() -> None:
    body = client().post("/api/v1/territory/polygon-profile", json={"coordinates": RING}).json()
    assert body["places"] == {"total": 17, "by_kind": {"comercio": 12, "alimentacao": 5}}
    assert body["buildings"]["count"] == 200
    assert body["buildings"]["coverage_ratio"] == 0.12
    assert body["grid"]["declividade"]["p90"] == 31.0
    assert body["grid"]["mb_classe"]["shares"] == {"24": 0.7, "3": 0.3}


def test_territory_images_and_building_tiles() -> None:
    c = client()
    [img] = c.get("/api/v1/territory/images").json()
    assert img["url"] == "territory/images/declividade.png"
    assert img["bounds"] == [-49.1, -27.3, -48.7, -26.9]
    r = c.get("/api/v1/" + img["url"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "public, max-age=3600"
    assert c.get("/api/v1/territory/images/ndvi.png").status_code == 404
    assert c.get("/api/v1/territory/images/NDVI.png").status_code == 404
    tile = c.get("/api/v1/territory/tiles/buildings/14/6000/9000.mvt")
    assert tile.status_code == 200
    assert tile.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    low = c.get("/api/v1/territory/tiles/buildings/10/300/500.mvt")
    assert low.status_code == 200
    assert low.content == b""
    assert c.get("/api/v1/territory/tiles/buildings/14/99999/0.mvt").status_code == 400
