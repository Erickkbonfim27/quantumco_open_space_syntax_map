from __future__ import annotations

from typing import Protocol
from uuid import UUID

from quantumco.identity.domain.email import EmailAddress, EmailMessage
from quantumco.identity.domain.user import User


class Mailer(Protocol):
    """Envia e-mail transacional (confirmação de cadastro, recuperação de senha)."""

    def send(self, message: EmailMessage) -> str:
        """Envia e devolve o ID do provedor."""
        ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password_hash: str, password: str) -> bool: ...


class UserRepository(Protocol):
    def add(self, user: User) -> None:
        """Grava o usuário; lança EmailAlreadyUsedError se o e-mail já existe."""
        ...

    def by_email(self, email: EmailAddress) -> User | None: ...

    def by_id(self, user_id: UUID) -> User | None: ...


class SessionStore(Protocol):
    def create(self, user_id: UUID) -> str:
        """Cria a sessão e devolve o token (só o hash fica gravado)."""
        ...

    def user_for(self, token: str) -> UUID | None: ...

    def revoke(self, token: str) -> None: ...


class EmailAlreadyUsedError(Exception):
    pass
