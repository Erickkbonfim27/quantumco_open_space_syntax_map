"""Casos de uso do perfil: ver e editar dados, foto e preferências.

Trocas de e-mail e de senha passam por link no e-mail: ver `account.py`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from quantumco.identity.application.ports import (
    AvatarStorageUnavailableError,
    AvatarStore,
    UserRepository,
)
from quantumco.identity.domain.avatar import Avatar, InvalidAvatarError
from quantumco.identity.domain.user import InvalidUserError, User
from quantumco.shared_kernel.clock import Clock

log = logging.getLogger(__name__)

_EXTENSION = {"image/webp": "webp", "image/jpeg": "jpg", "image/png": "png"}


class ProfileError(Exception):
    """Erro com mensagem pronta para o usuário."""


class WrongPasswordError(ProfileError):
    pass


class Profile:
    def __init__(self, *, users: UserRepository, avatars: AvatarStore | None, clock: Clock) -> None:
        self._users = users
        self._avatars = avatars
        self._clock = clock

    def update(
        self,
        user: User,
        *,
        name: str | None = None,
        organization: str | None = None,
        clear_organization: bool = False,
        preferences: Mapping[str, Any] | None = None,
    ) -> User:
        try:
            updated = user.with_profile(
                name=name,
                organization=organization,
                clear_organization=clear_organization,
                preferences=preferences,
            )
        except InvalidUserError as error:
            raise ProfileError(str(error)) from error
        self._users.update(updated, self._clock.now())
        return updated

    def _store(self) -> AvatarStore:
        if self._avatars is None:
            raise AvatarStorageUnavailableError("armazenamento de fotos não configurado (QC_S3_*)")
        return self._avatars

    def set_avatar(self, user: User, content: bytes) -> None:
        try:
            avatar = Avatar(content, "")
        except InvalidAvatarError as error:
            raise ProfileError(str(error)) from error
        store = self._store()
        now = self._clock.now()
        key = (
            f"avatars/{user.user_id}/{int(now.timestamp() * 1000)}.{_EXTENSION[avatar.media_type]}"
        )
        store.put(key, avatar.content, avatar.media_type)
        self._users.set_avatar(user.user_id, key, avatar.media_type, now)
        log.info("usuário %s trocou a foto (%d bytes)", user.user_id, len(avatar.content))
        self._forget(user.avatar_key)

    def remove_avatar(self, user: User) -> None:
        self._users.set_avatar(user.user_id, None, None, self._clock.now())
        self._forget(user.avatar_key)

    def avatar(self, user: User) -> Avatar | None:
        if not user.avatar_key or self._avatars is None:
            return None
        content = self._avatars.get(user.avatar_key)
        return Avatar(content, "") if content else None

    def _forget(self, key: str | None) -> None:
        """Apaga o arquivo antigo; se falhar, só registra (o usuário já tem a foto nova)."""
        if not key or self._avatars is None:
            return
        try:
            self._avatars.delete(key)
        except Exception:
            log.warning("não foi possível apagar a foto antiga %s", key, exc_info=True)
