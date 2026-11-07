from __future__ import annotations

from fastapi.testclient import TestClient

from quantumco.bootstrap.settings import Settings
from quantumco.entrypoints.api.app import create_app
from quantumco.road_network.application.queries import GetCurrentNetwork
from quantumco.syntax_analysis.application.queries import GetScenario, GetSyntaxMap

from ..fakes import Identity, cities, platform, territory
from ..support import METHODOLOGY_V1, MovableClock
from .test_api import NetworkReader, ScenarioReader, SyntaxReader
from .test_platform import sign_up

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
LOCAL = {"Origin": "http://localhost:5173"}


def setup() -> tuple[TestClient, Identity, MovableClock]:
    clock = MovableClock()
    ident = Identity(clock)
    settings = Settings.from_env(
        {
            "QC_METHODOLOGY_DIR": str(METHODOLOGY_V1),
            "QC_COOKIE_SECURE": "false",
            "QC_PUBLIC_BASE_URL": "https://quantumco.com.br/",
        }
    )
    app = create_app(
        settings,
        network_query=GetCurrentNetwork(NetworkReader(None)),
        syntax_query=GetSyntaxMap(SyntaxReader(None)),
        scenarios=GetScenario(ScenarioReader()),
        platform=platform(identity=ident, clock=clock),
        territory=territory(),
        cities=cities(),
    )
    return TestClient(app), ident, clock


def test_signup_sends_branded_confirmation_and_link_confirms() -> None:
    c, ident, _ = setup()
    user = sign_up(c)
    assert user["email_verified"] is False
    assert user["pending_email"] is None
    [mail] = ident.mailbox.sent
    assert mail.subject == "Confirme seu e-mail · quantumco"
    assert "https://quantumco.com.br/confirmar-email?token=" in mail.text
    assert mail.html is not None
    assert "QUANTUMCO" in mail.html
    assert "#2BD46B" in mail.html
    token = ident.mailbox.last_link()
    r = c.post("/api/v1/auth/confirm-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "verify_email"
    assert c.get("/api/v1/me").json()["user"]["email_verified"] is True
    again = c.post("/api/v1/auth/confirm-email", json={"token": token})
    assert again.status_code == 400  # uso único
    assert "inválido ou expirou" in again.json()["detail"]
    assert c.post("/api/v1/me/verification").status_code == 409  # já confirmado


def test_resend_verification_is_rate_limited_and_uses_local_origin() -> None:
    c, ident, clock = setup()
    sign_up(c)
    too_soon = c.post("/api/v1/me/verification")
    assert too_soon.status_code == 429
    clock.advance(seconds=61)
    r = c.post("/api/v1/me/verification", headers=LOCAL)
    assert r.status_code == 202
    assert r.json() == {"sent_to": "ana@exemplo.com"}
    assert "http://localhost:5173/confirmar-email?token=" in ident.mailbox.sent[-1].text
    # origem de fora não muda a base dos links (só localhost é aceito)
    clock.advance(seconds=61)
    c.post("/api/v1/me/verification", headers={"Origin": "https://ataque.exemplo"})
    assert "https://quantumco.com.br/confirmar-email" in ident.mailbox.sent[-1].text


def test_edit_name_organization_and_preferences() -> None:
    c, _, _ = setup()
    sign_up(c)
    r = c.patch(
        "/api/v1/me",
        json={"name": "Ana  Lima", "organization": "", "preferences": {"theme": "light"}},
    )
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    assert (user["name"], user["organization"], user["initials"]) == ("Ana Lima", None, "AL")
    assert user["preferences"] == {"theme": "light"}
    keeps = c.patch("/api/v1/me", json={"preferences": {"basemap": "satelite"}}).json()["user"]
    assert keeps["preferences"] == {"theme": "light", "basemap": "satelite"}
    assert c.patch("/api/v1/me", json={"preferences": {"theme": "roxo"}}).status_code == 400


def test_email_change_waits_for_confirmation_of_the_new_address() -> None:
    c, ident, clock = setup()
    sign_up(c)
    other = TestClient(c.app)
    sign_up(other, "bia@exemplo.com")
    wrong = c.post("/api/v1/me/email", json={"email": "nova@exemplo.com", "password": "errada!!"})
    assert wrong.status_code == 403
    taken = c.post("/api/v1/me/email", json={"email": "BIA@exemplo.com", "password": "segredo123"})
    assert taken.status_code == 400
    assert "outra conta" in taken.json()["detail"]

    r = c.post("/api/v1/me/email", json={"email": "nova@exemplo.com", "password": "segredo123"})
    assert r.status_code == 202, r.text
    assert r.json()["sent_to"] == "nova@exemplo.com"
    assert r.json()["user"]["email"] == "ana@exemplo.com"  # ainda não mudou
    assert r.json()["user"]["pending_email"] == "nova@exemplo.com"
    subjects = {str(m.to[0]): m.subject for m in ident.mailbox.sent[-2:]}
    assert subjects == {
        "nova@exemplo.com": "Confirme seu novo e-mail · quantumco",
        "ana@exemplo.com": "Pedido de troca de e-mail · quantumco",
    }

    token = ident.mailbox.last_link("nova@exemplo.com")
    done = c.post("/api/v1/auth/confirm-email", json={"token": token})
    assert done.status_code == 200
    assert done.json()["purpose"] == "change_email"
    me = c.get("/api/v1/me").json()["user"]
    assert (me["email"], me["pending_email"], me["email_verified"]) == (
        "nova@exemplo.com",
        None,
        True,
    )
    c.post("/api/v1/auth/logout")
    login = c.post(
        "/api/v1/auth/login", json={"email": "nova@exemplo.com", "password": "segredo123"}
    )
    assert login.status_code == 200

    # pedido cancelado: o link antigo deixa de valer
    clock.advance(seconds=61)
    c.post("/api/v1/me/email", json={"email": "outra@exemplo.com", "password": "segredo123"})
    stale = ident.mailbox.last_link("outra@exemplo.com")
    assert c.delete("/api/v1/me/email/pending").json()["user"]["pending_email"] is None
    assert c.post("/api/v1/auth/confirm-email", json={"token": stale}).status_code == 400


def test_password_change_goes_by_email_and_ends_all_sessions() -> None:
    c, ident, _ = setup()
    sign_up(c)
    laptop = TestClient(c.app)
    laptop.post("/api/v1/auth/login", json={"email": "ana@exemplo.com", "password": "segredo123"})
    r = c.post("/api/v1/me/password", headers=LOCAL)
    assert r.status_code == 202
    assert r.json() == {"sent_to": "ana@exemplo.com"}
    assert ident.mailbox.sent[-1].subject == "Troque sua senha · quantumco"
    assert "http://localhost:5173/redefinir-senha?token=" in ident.mailbox.sent[-1].text
    token = ident.mailbox.last_link()

    weak = c.post("/api/v1/auth/password/reset", json={"token": token, "new_password": "123"})
    assert weak.status_code == 400
    assert "8 caracteres" in weak.json()["detail"]
    fresh = TestClient(c.app)  # o link pode ser aberto em outro navegador
    ok = fresh.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "outra-senha-boa"}
    )
    assert ok.status_code == 200, ok.text
    assert fresh.get("/api/v1/me").status_code == 200  # já entra com a senha nova
    assert c.get("/api/v1/me").status_code == 401  # todas as outras sessões caíram
    assert laptop.get("/api/v1/me").status_code == 401
    assert ident.mailbox.sent[-1].subject == "Sua senha foi alterada · quantumco"
    reused = fresh.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "mais-uma-senha"}
    )
    assert reused.status_code == 400
    login = c.post(
        "/api/v1/auth/login", json={"email": "ana@exemplo.com", "password": "outra-senha-boa"}
    )
    assert login.status_code == 200


def test_forgot_password_never_reveals_accounts_and_links_expire() -> None:
    c, ident, clock = setup()
    sign_up(c)
    before = len(ident.mailbox.sent)
    unknown = c.post("/api/v1/auth/password/forgot", json={"email": "ninguem@exemplo.com"})
    assert unknown.status_code == 202
    assert unknown.json() == {"sent": True}
    assert len(ident.mailbox.sent) == before
    known = c.post("/api/v1/auth/password/forgot", json={"email": "ANA@exemplo.com"})
    assert known.json() == {"sent": True}
    assert ident.mailbox.sent[-1].subject == "Recupere sua senha · quantumco"
    # pedido repetido em menos de 1 min: mesma resposta, sem outro e-mail
    c.post("/api/v1/auth/password/forgot", json={"email": "ana@exemplo.com"})
    assert len(ident.mailbox.sent) == before + 1
    token = ident.mailbox.last_link()
    clock.advance(hours=1, seconds=1)
    late = c.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "nova-senha-1"}
    )
    assert late.status_code == 400


def test_mail_provider_down_answers_502() -> None:
    c, ident, _ = setup()
    sign_up(c)  # o cadastro passa mesmo sem e-mail
    ident.mailbox.down = True
    r = c.post("/api/v1/me/password")
    assert r.status_code == 502
    assert "Não foi possível enviar" in r.json()["detail"]


def test_avatar_upload_serve_replace_and_remove() -> None:
    c, ident, clock = setup()
    sign_up(c)
    assert c.get("/api/v1/me").json()["user"]["avatar_url"] is None
    fake = c.put("/api/v1/me/avatar", content=b"<svg onload=alert(1)>")
    assert fake.status_code == 400
    up = c.put("/api/v1/me/avatar", content=WEBP, headers={"Content-Type": "image/png"})
    assert up.status_code == 200, up.text
    url = up.json()["user"]["avatar_url"]
    assert url.startswith("/api/v1/me/avatar?v=")
    [key] = ident.files.objects
    assert key.startswith("avatars/")
    assert key.endswith(".webp")
    got = c.get(url)
    assert got.content == WEBP
    assert got.headers["content-type"] == "image/webp"  # pelo conteúdo, não pelo cabeçalho
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in got.headers["cache-control"]
    clock.advance(seconds=5)
    c.put("/api/v1/me/avatar", content=PNG)
    [key2] = ident.files.objects  # a foto antiga foi apagada do armazenamento
    assert key2 != key
    assert key2.endswith(".png")
    assert c.put("/api/v1/me/avatar", content=PNG + b"\x00" * 600_000).status_code == 413
    gone = c.delete("/api/v1/me/avatar").json()["user"]
    assert gone["avatar_url"] is None
    assert ident.files.objects == {}
    assert c.get("/api/v1/me/avatar").status_code == 404
