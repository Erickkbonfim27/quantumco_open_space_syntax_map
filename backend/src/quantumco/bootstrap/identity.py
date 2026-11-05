from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.identity.application.ports import Mailer
from quantumco.identity.domain.email import EmailAddress, Sender
from quantumco.identity.infrastructure.log_mailer import LogMailer
from quantumco.identity.infrastructure.resend_mailer import ResendMailer


def sender_from(settings: Settings) -> Sender:
    return Sender(address=EmailAddress(settings.mail_from), display_name=settings.mail_from_name)


def build_mailer(settings: Settings) -> Mailer:
    """Resend quando há chave; senão, só log (desenvolvimento)."""
    sender = sender_from(settings)
    if settings.resend_api_key:
        return ResendMailer(api_key=settings.resend_api_key, sender=sender)
    return LogMailer(sender)
