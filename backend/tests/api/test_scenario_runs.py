from __future__ import annotations

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.queries import GetCurrentNetwork
from quantumco.scenarios.domain.run import RunQuota
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap

from ..fakes import Queue, platform, territory
from ..support import METHODOLOGY_V1
from .test_api import NetworkReader, ScenarioReader, SyntaxReader
from .test_platform import sign_up

LINE = [[-48.92, -27.10], [-48.915, -27.095]]


def client(queue: Queue | None = None, quota: RunQuota | None = None) -> TestClient:
    settings = Settings.from_env(
        {"QC_METHODOLOGY_DIR": str(METHODOLOGY_V1), "QC_COOKIE_SECURE": "false"}
    )
    app = create_app(
        settings,
        network_query=GetCurrentNetwork(NetworkReader(None)),
        syntax_query=GetSyntaxMap(SyntaxReader(None)),
        scenarios=GetScenario(ScenarioReader()),
        platform=platform(queue=queue, quota=quota),
        territory=territory(),
    )
    return TestClient(app)


def workspace(c: TestClient) -> str:
    sign_up(c)
    return str(c.post("/api/v1/workspaces", json={"name": "Ponte nova"}).json()["id"])


def test_edits_are_saved_with_the_workspace() -> None:
    c = client()
    ws = workspace(c)
    edits = [
        {"type": "close", "link_id": "12"},
        {"type": "add", "coords": LINE, "label": "ligação"},
        {"type": "reroute", "link_id": "40", "coords": LINE},
    ]
    r = c.put(f"/api/v1/workspaces/{ws}/edits", json={"edits": edits})
    assert r.status_code == 200, r.text
    assert [e["type"] for e in r.json()["edits"]] == ["close", "add", "reroute"]
    assert c.get(f"/api/v1/workspaces/{ws}").json()["edits_count"] == 3
    twice = c.put(
        f"/api/v1/workspaces/{ws}/edits",
        json={"edits": [{"type": "remove", "link_id": "12"}, {"type": "close", "link_id": "12"}]},
    )
    assert twice.status_code == 400
    assert "já tem uma alteração" in twice.json()["detail"]


def test_run_needs_edits_and_enters_the_queue() -> None:
    queue = Queue()
    c = client(queue)
    ws = workspace(c)
    empty = c.post(f"/api/v1/workspaces/{ws}/runs")
    assert empty.status_code == 409
    assert "pelo menos uma edição" in empty.json()["detail"]

    c.put(f"/api/v1/workspaces/{ws}/edits", json={"edits": [{"type": "remove", "link_id": "1"}]})
    r = c.post(f"/api/v1/workspaces/{ws}/runs")
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["status"] == "queued"
    assert run["queue"] == {"position": 1, "running": 0, "workers": 2}
    assert len(queue.jobs) == 1

    again = c.post(f"/api/v1/workspaces/{ws}/runs")
    assert again.status_code == 409
    assert "já está sendo calculado" in again.json()["detail"]

    latest = c.get(f"/api/v1/workspaces/{ws}/runs/latest").json()
    assert latest["id"] == run["id"]
    canceled = c.delete(f"/api/v1/workspaces/{ws}/runs/{run['id']}")
    assert canceled.json()["status"] == "canceled"


def test_queue_down_answers_503_and_marks_the_run() -> None:
    c = client(Queue(down=True))
    ws = workspace(c)
    c.put(f"/api/v1/workspaces/{ws}/edits", json={"edits": [{"type": "remove", "link_id": "1"}]})
    r = c.post(f"/api/v1/workspaces/{ws}/runs")
    assert r.status_code == 503
    assert c.get(f"/api/v1/workspaces/{ws}/runs/latest").json()["status"] == "failed"


def test_daily_quota() -> None:
    c = client(quota=RunQuota(active_per_user=5, daily_per_user=1))
    ws = workspace(c)
    c.put(f"/api/v1/workspaces/{ws}/edits", json={"edits": [{"type": "remove", "link_id": "1"}]})
    first = c.post(f"/api/v1/workspaces/{ws}/runs").json()
    c.delete(f"/api/v1/workspaces/{ws}/runs/{first['id']}")  # cancelado não conta
    assert c.post(f"/api/v1/workspaces/{ws}/runs").status_code == 202
    other = str(c.post("/api/v1/workspaces", json={"name": "Outro"}).json()["id"])
    c.put(f"/api/v1/workspaces/{other}/edits", json={"edits": [{"type": "close", "link_id": "2"}]})
    refused = c.post(f"/api/v1/workspaces/{other}/runs")
    assert refused.status_code == 409
    assert "por dia" in refused.json()["detail"]


def test_runs_and_results_are_private() -> None:
    owner = client()
    ws = workspace(owner)
    assert owner.get(f"/api/v1/workspaces/{ws}/result/links").status_code == 404
    stranger = TestClient(owner.app)
    sign_up(stranger, "bia@exemplo.com")
    assert stranger.get(f"/api/v1/workspaces/{ws}/runs/latest").status_code == 404
    assert stranger.get(f"/api/v1/workspaces/{ws}/result/manifest").status_code == 404
    # resultados de usuário nunca aparecem na rota pública de cenários
    assert owner.get(f"/api/v1/scenarios/ws-{ws}/links").status_code == 404
