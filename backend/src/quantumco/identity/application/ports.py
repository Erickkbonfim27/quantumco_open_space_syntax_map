from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from quantumco.identity.domain.email import EmailAddress, EmailMessage
from quantumco.identity.domain.tokens import EmailToken, TokenPurpose
from quantumco.identity.domain.user import User


class MailDeliveryError(RuntimeError):
    """O provedor de e-mail não aceitou a mensagem (fora do ar, chave inválida…)."""


class Mailer(Protocol):
    """Envia e-mail transacional (confirmação de cadastro, recuperação de senha)."""

    def send(self, message: EmailMessage) -> str:
        """Envia e devolve o ID do provedor; lança MailDeliveryError se não deu."""
        ...


class AccountMessages(Protocol):
    """Monta os e-mails da conta (texto e HTML no design da marca)."""

    def confirm_email(self, *, to: EmailAddress, name: str, link: str) -> EmailMessage: ...

    def confirm_new_email(
        self, *, to: EmailAddress, name: str, link: str, old_email: EmailAddress
    ) -> EmailMessage: ...

    def email_change_notice(
        self, *, to: EmailAddress, name: str, new_email: EmailAddress, profile_link: str
    ) -> EmailMessage: ...

    def password_link(
        self, *, to: EmailAddress, name: str, link: str, forgot: bool
    ) -> EmailMessage: ...

    def password_changed(
        self, *, to: EmailAddress, name: str, when: datetime, recover_link: str
    ) -> EmailMessage: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class UserRepository(Protocol):
    def add(self, user: User) -> None:
        """Grava o usuário; lança EmailAlreadyUsedError se o e-mail já existe."""
        ...

    def by_email(self, email: EmailAddress) -> User | None: ...

    def by_id(self, user_id: UUID) -> User | None: ...

    def update(self, user: User, now: datetime) -> None:
        """Grava nome, organização, e-mail (e o pendente), verificação, senha e preferências;
        EmailAlreadyUsedError se o e-mail novo já é de outra conta."""
        ...

    def set_avatar(
        self, user_id: UUID, key: str | None, media_type: str | None, now: datetime
    ) -> None:
        """Aponta a foto do usuário para um objeto do armazenamento (None remove)."""
        ...


class SessionStore(Protocol):
    def create(self, user_id: UUID) -> str:
        """Cria a sessão e devolve o token (só o hash fica gravado)."""
        ...

    def user_for(self, token: str) -> UUID | None: ...

    def revoke(self, token: str) -> None: ...

    def revoke_all(self, user_id: UUID) -> int:
        """Encerra todas as sessões do usuário (senha nova); devolve quantas."""
        ...


class TokenStore(Protocol):
    def issue(
        self,
        user_id: UUID,
        purpose: TokenPurpose,
        *,
        now: datetime,
        ttl: timedelta,
        new_email: EmailAddress | None = None,
    ) -> str:
        """Cria o link (invalida os anteriores do mesmo tipo) e devolve o token em claro."""
        ...

    def consume(
        self, token: str, purposes: tuple[TokenPurpose, ...], now: datetime
    ) -> EmailToken | None:
        """Usa o link uma única vez.

        None se ele não existe, expirou, já foi usado ou é de outro tipo."""
        ...

    def last_issued(self, user_id: UUID, purpose: TokenPurpose) -> datetime | None: ...


class AvatarStorageUnavailableError(RuntimeError):
    pass


class AvatarStore(Protocol):
    """Arquivos das fotos de perfil (RustFS/S3)."""

    def put(self, key: str, content: bytes, media_type: str) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def delete(self, key: str) -> None: ...


class EmailAlreadyUsedError(Exception):
    pass
