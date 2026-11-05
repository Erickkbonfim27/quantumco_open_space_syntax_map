"""Casos de uso de autenticação: cadastro, login, logout e usuário da sessão."""

from __future__ import annotations

from dataclasses import dataclass

from quantumco.identity.application.ports import (
    EmailAlreadyUsedError,
    PasswordHasher,
    SessionStore,
    UserRepository,
)
from quantumco.identity.domain.email import EmailAddress, InvalidEmailError
from quantumco.identity.domain.user import InvalidUserError, User, check_password_policy
from quantumco.shared_kernel.clock import Clock

# hash de referência para que login com e-mail inexistente leve o mesmo tempo (anti-enumeração)
_DUMMY_PASSWORD = "senha-que-nao-existe-0000"


class AuthError(Exception):
    """Erro com mensagem pronta para o usuário."""


@dataclass(frozen=True, slots=True)
class Session:
    user: User
    token: str


class Authentication:
    def __init__(
        self, *, users: UserRepository, hasher: PasswordHasher, sessions: SessionStore, clock: Clock
    ) -> None:
        self._users = users
        self._hasher = hasher
        self._sessions = sessions
        self._clock = clock
        self._dummy_hash = hasher.hash(_DUMMY_PASSWORD)

    def sign_up(self, *, name: str, email: str, organization: str | None, password: str) -> Session:
        try:
            address = EmailAddress(email)
            check_password_policy(password)
            user = User.register(
                name=name,
                email=address,
                organization=organization,
                password_hash=self._hasher.hash(password),
                now=self._clock.now(),
            )
            self._users.add(user)
        except InvalidEmailError as error:
            raise AuthError("Informe um e-mail válido.") from error
        except InvalidUserError as error:
            raise AuthError(str(error)) from error
        except EmailAlreadyUsedError as error:
            raise AuthError("Já existe uma conta com esse e-mail. Entre com ela.") from error
        return Session(user=user, token=self._sessions.create(user.user_id))

    def log_in(self, *, email: str, password: str) -> Session:
        try:
            address = EmailAddress(email)
        except InvalidEmailError as error:
            raise AuthError("Informe um e-mail válido.") from error
        user = self._users.by_email(address)
        stored = user.password_hash if user else self._dummy_hash
        ok = self._hasher.verify(stored, password)
        if user is None or not ok:
            raise AuthError("E-mail ou senha incorretos.")
        return Session(user=user, token=self._sessions.create(user.user_id))

    def log_out(self, token: str) -> None:
        self._sessions.revoke(token)

    def current_user(self, token: str | None) -> User | None:
        if not token:
            return None
        user_id = self._sessions.user_for(token)
        return self._users.by_id(user_id) if user_id else None
