from __future__ import annotations

from typing import Protocol

from quantumco.identity.domain.email import EmailMessage


class Mailer(Protocol):
    """Envia e-mail transacional (confirmação de cadastro, recuperação de senha)."""

    def send(self, message: EmailMessage) -> str:
        """Envia e devolve o ID do provedor."""
        ...
