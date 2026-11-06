"""Fluxos de conta por e-mail: confirmar endereço, trocar e-mail e criar senha nova.

Todos usam links de uso único (ver `domain/tokens.py`). Mudanças sensíveis só valem depois
do clique no link: o e-mail novo só passa a valer confirmado; a senha só muda pelo link
enviado ao e-mail da conta (troca pedida no perfil ou "esqueci a senha").
"""

from __future__ import annotations

import logging

from quantumco.identity.application.auth import Session
from quantumco.identity.application.ports import (
    AccountMessages,
    EmailAlreadyUsedError,
    Mailer,
    PasswordHasher,
    SessionStore,
    TokenStore,
    UserRepository,
)
from quantumco.identity.application.profile import ProfileError, WrongPasswordError
from quantumco.identity.domain.email import EmailAddress, EmailMessage, InvalidEmailError
from quantumco.identity.domain.tokens import TOKEN_TTL, TokenPurpose, too_soon
from quantumco.identity.domain.user import InvalidUserError, User, check_password_policy
from quantumco.shared_kernel.clock import Clock

log = logging.getLogger(__name__)

CONFIRM_PATH = "/confirmar-email"
RESET_PATH = "/redefinir-senha"
FORGOT_PATH = "/esqueci-senha"
PROFILE_PATH = "/perfil"


class InvalidLinkError(ProfileError):
    """Link inexistente, expirado, já usado ou de outro tipo."""


class TooSoonError(ProfileError):
    """Outro e-mail do mesmo tipo foi enviado há menos de um minuto."""


class AlreadyVerifiedError(ProfileError):
    pass


class AccountEmails:
    def __init__(
        self,
        *,
        users: UserRepository,
        tokens: TokenStore,
        sessions: SessionStore,
        hasher: PasswordHasher,
        mailer: Mailer,
        messages: AccountMessages,
        clock: Clock,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._sessions = sessions
        self._hasher = hasher
        self._mailer = mailer
        self._messages = messages
        self._clock = clock

    # ------------------------------------------------------------------ apoio

    def _issue(
        self, user: User, purpose: TokenPurpose, new_email: EmailAddress | None = None
    ) -> str:
        now = self._clock.now()
        if too_soon(self._tokens.last_issued(user.user_id, purpose), now):
            raise TooSoonError(
                "Já enviamos um e-mail há instantes. Aguarde um minuto para pedir outro."
            )
        return self._tokens.issue(
            user.user_id, purpose, now=now, ttl=TOKEN_TTL[purpose], new_email=new_email
        )

    def _send(self, message: EmailMessage, what: str, user: User) -> None:
        message_id = self._mailer.send(message)  # MailDeliveryError sobe para a API (502)
        log.info("e-mail '%s' para o usuário %s: %s", what, user.user_id, message_id)

    @staticmethod
    def _link(base_url: str, path: str, token: str) -> str:
        return f"{base_url.rstrip('/')}{path}?token={token}"

    # ------------------------------------------------------------------ confirmação de e-mail

    def send_verification(self, user: User, base_url: str) -> EmailAddress:
        if user.email_verified:
            raise AlreadyVerifiedError("Seu e-mail já está confirmado.")
        token = self._issue(user, TokenPurpose.VERIFY_EMAIL)
        link = self._link(base_url, CONFIRM_PATH, token)
        self._send(
            self._messages.confirm_email(to=user.email, name=user.name, link=link),
            "confirmar",
            user,
        )
        return user.email

    def confirm(self, token: str) -> tuple[User, TokenPurpose]:
        """Clique no link de confirmação (cadastro ou troca de e-mail)."""
        now = self._clock.now()
        used = self._tokens.consume(
            token, (TokenPurpose.VERIFY_EMAIL, TokenPurpose.CHANGE_EMAIL), now
        )
        user = self._users.by_id(used.user_id) if used else None
        if used is None or user is None:
            raise InvalidLinkError("Este link é inválido ou expirou. Peça um novo no seu perfil.")
        if used.purpose == TokenPurpose.VERIFY_EMAIL:
            updated = user.confirm_email(now)
        else:
            # só vale o pedido mais recente: um link antigo não troca para outro endereço
            if used.new_email is None or user.pending_email != used.new_email:
                raise InvalidLinkError("Este link de troca de e-mail não vale mais. Peça de novo.")
            updated = user.apply_pending_email(used.new_email, now)
        try:
            self._users.update(updated, now)
        except EmailAlreadyUsedError as error:
            raise ProfileError("Esse e-mail passou a ser usado por outra conta.") from error
        log.info("usuário %s confirmou o e-mail (%s)", user.user_id, used.purpose.value)
        return updated, used.purpose

    # ------------------------------------------------------------------ troca de e-mail

    def request_email_change(
        self, user: User, *, email: str, password: str, base_url: str
    ) -> tuple[User, EmailAddress]:
        try:
            address = EmailAddress(email)
        except InvalidEmailError as error:
            raise ProfileError("Informe um e-mail válido.") from error
        if not self._hasher.verify(user.password_hash, password):
            raise WrongPasswordError("Senha atual incorreta.")
        if address == user.email:
            raise ProfileError("Esse já é o e-mail da sua conta.")
        if self._users.by_email(address) is not None:
            raise ProfileError("Esse e-mail já é usado por outra conta.")
        token = self._issue(user, TokenPurpose.CHANGE_EMAIL, new_email=address)
        updated = user.with_pending_email(address)
        self._users.update(updated, self._clock.now())
        link = self._link(base_url, CONFIRM_PATH, token)
        self._send(
            self._messages.confirm_new_email(
                to=address, name=user.name, link=link, old_email=user.email
            ),
            "confirmar e-mail novo",
            user,
        )
        try:  # aviso ao endereço antigo: se falhar, a troca segue (o novo já recebeu o link)
            self._mailer.send(
                self._messages.email_change_notice(
                    to=user.email,
                    name=user.name,
                    new_email=address,
                    profile_link=f"{base_url.rstrip('/')}{PROFILE_PATH}",
                )
            )
        except Exception:
            log.warning("aviso de troca de e-mail não enviado ao endereço antigo", exc_info=True)
        return updated, address

    def cancel_email_change(self, user: User) -> User:
        updated = user.with_pending_email(None)
        self._users.update(updated, self._clock.now())
        return updated

    # ------------------------------------------------------------------ senha

    def request_password_change(self, user: User, base_url: str) -> EmailAddress:
        """Troca de senha pedida no perfil: o link vai para o e-mail da conta."""
        token = self._issue(user, TokenPurpose.RESET_PASSWORD)
        link = self._link(base_url, RESET_PATH, token)
        self._send(
            self._messages.password_link(to=user.email, name=user.name, link=link, forgot=False),
            "trocar senha",
            user,
        )
        return user.email

    def forgot_password(self, email: str, base_url: str) -> None:
        """Sempre responde igual, exista ou não a conta (não revela quem tem cadastro)."""
        try:
            address = EmailAddress(email)
        except InvalidEmailError as error:
            raise ProfileError("Informe um e-mail válido.") from error
        user = self._users.by_email(address)
        if user is None:
            log.info("recuperação de senha pedida para e-mail sem conta")
            return
        try:
            token = self._issue(user, TokenPurpose.RESET_PASSWORD)
        except TooSoonError:
            return
        link = self._link(base_url, RESET_PATH, token)
        self._send(
            self._messages.password_link(to=user.email, name=user.name, link=link, forgot=True),
            "recuperar senha",
            user,
        )

    def reset_password(self, token: str, new_password: str, base_url: str) -> Session:
        try:
            check_password_policy(new_password)
        except InvalidUserError as error:
            raise ProfileError(str(error)) from error
        now = self._clock.now()
        used = self._tokens.consume(token, (TokenPurpose.RESET_PASSWORD,), now)
        user = self._users.by_id(used.user_id) if used else None
        if used is None or user is None:
            raise InvalidLinkError("Este link é inválido ou expirou. Peça um novo.")
        # quem clicou no link provou que lê este e-mail
        updated = user.with_password_hash(self._hasher.hash(new_password)).confirm_email(now)
        self._users.update(updated, now)
        ended = self._sessions.revoke_all(user.user_id)
        log.info("usuário %s criou senha nova (%d sessões encerradas)", user.user_id, ended)
        try:
            self._mailer.send(
                self._messages.password_changed(
                    to=user.email,
                    name=user.name,
                    when=now,
                    recover_link=f"{base_url.rstrip('/')}{FORGOT_PATH}",
                )
            )
        except Exception:
            log.warning("aviso de senha alterada não enviado", exc_info=True)
        return Session(user=updated, token=self._sessions.create(user.user_id))
