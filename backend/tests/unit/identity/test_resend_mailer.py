from __future__ import annotations

import json

import httpx
import pytest

from quantumco.identity.domain.email import EmailAddress, EmailMessage, Sender
from quantumco.identity.infrastructure.resend_mailer import (
    API_URL,
    MailerError,
    ResendMailer,
    RestrictedApiKeyError,
)

SENDER = Sender(EmailAddress("spacesyntax@erickkbonfim.com.br"), "quantumco")
MESSAGE = EmailMessage(to=(EmailAddress("dono@exemplo.com"),), subject="Oi", text="corpo")


def mailer(handler: httpx.MockTransport, waits: list[float] | None = None) -> ResendMailer:
    return ResendMailer(
        api_key="re_test",
        sender=SENDER,
        client=httpx.Client(base_url=API_URL, transport=handler),
        initial_backoff_s=1.0,
        sleep=(waits if waits is not None else []).append,
    )


def test_send_posts_expected_payload() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "abc-123"})

    assert mailer(httpx.MockTransport(handle)).send(MESSAGE) == "abc-123"
    request = seen[0]
    assert request.url.path == "/emails"
    assert request.headers["Authorization"] == "Bearer re_test"
    assert json.loads(request.content) == {
        "from": '"quantumco" <spacesyntax@erickkbonfim.com.br>',
        "to": ["dono@exemplo.com"],
        "subject": "Oi",
        "text": "corpo",
    }


def test_retries_on_rate_limit() -> None:
    statuses = iter([429, 200])
    waits: list[float] = []

    def handle(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        return httpx.Response(status, json={"id": "ok"} if status == 200 else {})

    assert mailer(httpx.MockTransport(handle), waits).send(MESSAGE) == "ok"
    assert waits == [1.0]


def test_client_error_is_raised_without_leaking_key() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, json={"name": "validation_error", "message": "domain not verified"}
        )

    with pytest.raises(MailerError, match="403") as error:
        mailer(httpx.MockTransport(handle)).send(MESSAGE)
    assert "re_test" not in str(error.value)


def test_domain_status() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"name": "erickkbonfim.com.br", "status": "verified"}]}
        )

    m = mailer(httpx.MockTransport(handle))
    assert m.domain_status("erickkbonfim.com.br") == "verified"
    assert m.domain_status("outro.com") is None


def test_restricted_key_is_reported_distinctly() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"statusCode": 401, "name": "restricted_api_key", "message": "only send"}
        )

    with pytest.raises(RestrictedApiKeyError):
        mailer(httpx.MockTransport(handle)).domain_status("erickkbonfim.com.br")
