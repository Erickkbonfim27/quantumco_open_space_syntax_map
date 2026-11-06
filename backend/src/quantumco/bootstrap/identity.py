from __future__ import annotations

from quantumco.bootstrap.settings import Settings
from quantumco.identity.application.ports import AvatarStore, Mailer
from quantumco.identity.domain.email import EmailAddress, Sender
from quantumco.identity.infrastructure.log_mailer import LogMailer
from quantumco.identity.infrastructure.redirect_mailer import RedirectingMailer
from quantumco.identity.infrastructure.resend_mailer import ResendMailer


def sender_from(settings: Settings) -> Sender:
    return Sender(address=EmailAddress(settings.mail_from), display_name=settings.mail_from_name)


def build_mailer(settings: Settings) -> Mailer:
    """Resend quando há chave; senão, só log (desenvolvimento).

    Na homologação (dados reais copiados da produção) tudo vai para OWNER_EMAIL; sem OWNER_EMAIL,
    nada sai: só log.
    """
    sender = sender_from(settings)
    if settings.use_homolog:
        if not (settings.resend_api_key and settings.owner_email):
            return LogMailer(sender)
        inner = ResendMailer(api_key=settings.resend_api_key, sender=sender)
        return RedirectingMailer(inner, EmailAddress(settings.owner_email))
    if settings.resend_api_key:
        return ResendMailer(api_key=settings.resend_api_key, sender=sender)
    return LogMailer(sender)


def build_avatar_store(settings: Settings) -> AvatarStore | None:
    """Fotos de perfil no RustFS; sem QC_S3_*, o envio de foto responde 503."""
    if not settings.s3_configured:
        return None
    from quantumco.identity.infrastructure.s3_avatars import S3AvatarStore  # noqa: PLC0415

    return S3AvatarStore(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        bucket=settings.s3_bucket_avatars,
    )
