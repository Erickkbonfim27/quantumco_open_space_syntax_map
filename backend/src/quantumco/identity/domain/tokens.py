"""Links enviados por e-mail: confirmar endereço, trocar e-mail e criar senha nova.

O token vai só no link; o banco guarda o sha256. Cada link vale uma vez e por pouco tempo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from quantumco.identity.domain.email import EmailAddress


class TokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    CHANGE_EMAIL = "change_email"
    RESET_PASSWORD = "reset_password"


TOKEN_TTL: dict[TokenPurpose, timedelta] = {
    TokenPurpose.VERIFY_EMAIL: timedelta(hours=48),
    TokenPurpose.CHANGE_EMAIL: timedelta(hours=48),
    TokenPurpose.RESET_PASSWORD: timedelta(hours=1),
}
# intervalo mínimo entre dois e-mails do mesmo tipo para a mesma conta
RESEND_INTERVAL = timedelta(seconds=60)


@dataclass(frozen=True, slots=True)
class EmailToken:
    """Um link já usado (consumido): quem é, para quê e, na troca, o e-mail novo."""

    user_id: UUID
    purpose: TokenPurpose
    new_email: EmailAddress | None
    created_at: datetime


def too_soon(last_issued: datetime | None, now: datetime) -> bool:
    return last_issued is not None and now - last_issued < RESEND_INTERVAL
