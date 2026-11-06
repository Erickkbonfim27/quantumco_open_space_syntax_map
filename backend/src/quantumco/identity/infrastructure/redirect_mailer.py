"""Adaptador `Mailer` da homologação: todo e-mail vai para o dono do projeto (OWNER_EMAIL).

A homologação é uma cópia fiel da produção, com contas e e-mails reais. Sem este desvio, um teste
de cadastro, troca de senha ou aviso de cenário escreveria para um usuário de verdade.
"""

from __future__ import annotations

from dataclasses import replace

from quantumco.identity.application.ports import Mailer
from quantumco.identity.domain.email import EmailAddress, EmailMessage


class RedirectingMailer:
    def __init__(self, inner: Mailer, to: EmailAddress) -> None:
        self._inner = inner
        self._to = to

    def send(self, message: EmailMessage) -> str:
        original = ", ".join(str(a) for a in message.to)
        note = f"[homologação] destinatário original: {original}"
        return self._inner.send(
            replace(
                message,
                to=(self._to,),
                subject=f"[homologação] {message.subject}",
                text=f"{note}\n\n{message.text}",
                html=(
                    f"<p style='font:12px monospace;color:#b45309'>{note}</p>{message.html}"
                    if message.html
                    else None
                ),
            )
        )
