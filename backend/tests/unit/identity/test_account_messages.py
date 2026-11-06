from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from quantumco.identity.domain.email import EmailAddress
from quantumco.identity.domain.tokens import RESEND_INTERVAL, TOKEN_TTL, TokenPurpose, too_soon
from quantumco.identity.infrastructure.email_templates import BrandedAccountMessages

TO = EmailAddress("ana@exemplo.com")
LINK = "https://quantumco.com.br/redefinir-senha?token=abc&x=<1>"


def test_every_message_has_text_html_and_escapes_user_values() -> None:
    m = BrandedAccountMessages()
    messages = [
        m.confirm_email(to=TO, name="<script>x</script> Souza", link=LINK),
        m.confirm_new_email(to=TO, name="<b>Ana</b>", link=LINK, old_email=TO),
        m.email_change_notice(to=TO, name="Ana", new_email=TO, profile_link=LINK),
        m.password_link(to=TO, name="Ana", link=LINK, forgot=True),
        m.password_link(to=TO, name="Ana", link=LINK, forgot=False),
        m.password_changed(
            to=TO, name="Ana", when=datetime(2026, 11, 6, 2, 30, tzinfo=UTC), recover_link=LINK
        ),
    ]
    for message in messages:
        assert message.html is not None
        assert message.subject.endswith("· quantumco")
        assert "quantumco.com.br" in message.text
        assert "<script>" not in message.html
        assert "<b>Ana</b>" not in message.html
        assert "x=&lt;1&gt;" in message.html  # o link também é escapado
        assert "x=<1>" not in message.html
        assert 'role="presentation"' in message.html  # layout em tabelas (clientes de e-mail)
    assert "05/11/2026 às 23:30" in messages[-1].text  # 02:30 UTC = 23:30 em Brasília


def test_token_rules() -> None:
    now = datetime(2026, 11, 8, tzinfo=UTC)
    assert TOKEN_TTL[TokenPurpose.RESET_PASSWORD] == timedelta(hours=1)
    assert TOKEN_TTL[TokenPurpose.VERIFY_EMAIL] == timedelta(hours=48)
    assert too_soon(now - timedelta(seconds=10), now)
    assert not too_soon(now - RESEND_INTERVAL, now)
    assert not too_soon(None, now)


@pytest.mark.parametrize("endpoint", ["rustfs.exemplo", "https://rustfs.exemplo:9000/"])
def test_s3_store_accepts_endpoint_forms(endpoint: str) -> None:
    from quantumco.identity.infrastructure.s3_avatars import S3AvatarStore  # noqa: PLC0415

    S3AvatarStore(endpoint=endpoint, access_key="a", secret_key="b", region="", bucket="x")
