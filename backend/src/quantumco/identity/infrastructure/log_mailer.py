"""Adaptador `Mailer` de desenvolvimento: só escreve o e-mail no log."""

from __future__ import annotations

import logging
from uuid import uuid4

from quantumco.identity.domain.email import EmailMessage, Sender

log = logging.getLogger(__name__)


class LogMailer:
    def __init__(self, sender: Sender) -> None:
        self._sender = sender
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> str:
        self.sent.append(message)
        message_id = f"log-{uuid4()}"
        log.info(
            "[e-mail NÃO enviado: sem RESEND_API_KEY] de %s para %s — %s\n%s",
            self._sender.formatted(),
            ", ".join(str(a) for a in message.to),
            message.subject,
            message.text,
        )
        return message_id
