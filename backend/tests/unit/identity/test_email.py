from __future__ import annotations

import pytest

from quantumco.identity.domain.email import EmailAddress, EmailMessage, InvalidEmailError, Sender


def test_email_is_normalized() -> None:
    address = EmailAddress("  SpaceSyntax@ErickKBonfim.com.br ")
    assert str(address) == "spacesyntax@erickkbonfim.com.br"
    assert address.domain == "erickkbonfim.com.br"


@pytest.mark.parametrize("raw", ["", "sem-arroba", "a@b", "a b@c.com", "a@@c.com"])
def test_invalid_email(raw: str) -> None:
    with pytest.raises(InvalidEmailError):
        EmailAddress(raw)


def test_sender_formatting_strips_quotes() -> None:
    sender = Sender(EmailAddress("spacesyntax@erickkbonfim.com.br"), 'quantumco "Brusque"')
    assert sender.formatted() == '"quantumco Brusque" <spacesyntax@erickkbonfim.com.br>'
    assert Sender(EmailAddress("a@b.com")).formatted() == "a@b.com"


def test_message_requires_recipient_subject_and_text() -> None:
    to = (EmailAddress("a@b.com"),)
    with pytest.raises(ValueError, match="destinatário"):
        EmailMessage(to=(), subject="x", text="y")
    with pytest.raises(ValueError, match="assunto"):
        EmailMessage(to=to, subject=" ", text="y")
    with pytest.raises(ValueError, match="corpo"):
        EmailMessage(to=to, subject="x", text="")
