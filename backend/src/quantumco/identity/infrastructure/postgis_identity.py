from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg import errors
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from quantumco.identity.application.ports import EmailAlreadyUsedError
from quantumco.identity.domain.email import EmailAddress
from quantumco.identity.domain.tokens import EmailToken, TokenPurpose
from quantumco.identity.domain.user import User

SESSION_DAYS = 30


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class PostgisUserRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def add(self, user: User) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    "insert into identity.users (user_id, name, email, organization, "
                    "password_hash, created_at) values (%s, %s, %s, %s, %s, %s)",
                    (
                        user.user_id,
                        user.name,
                        str(user.email),
                        user.organization,
                        user.password_hash,
                        user.created_at,
                    ),
                )
        except errors.UniqueViolation as error:
            raise EmailAlreadyUsedError(str(user.email)) from error

    def _one(self, where: str, value: object) -> User | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select user_id, name, email, organization, password_hash, created_at, "
                "preferences, avatar_updated_at, avatar_key, email_verified_at, pending_email "
                f"from identity.users where {where} = %s",
                (value,),
            ).fetchone()
        if row is None:
            return None
        return User(
            user_id=row[0],
            name=row[1],
            email=EmailAddress(row[2]),
            organization=row[3],
            password_hash=row[4],
            created_at=row[5],
            preferences=row[6] or {},
            avatar_updated_at=row[7],
            avatar_key=row[8],
            email_verified_at=row[9],
            pending_email=EmailAddress(row[10]) if row[10] else None,
        )

    def by_email(self, email: EmailAddress) -> User | None:
        return self._one("email", str(email))

    def by_id(self, user_id: UUID) -> User | None:
        return self._one("user_id", user_id)

    def update(self, user: User, now: datetime) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    "update identity.users set name = %s, email = %s, organization = %s, "
                    "password_hash = %s, preferences = %s, pending_email = %s, "
                    "email_verified_at = %s, updated_at = %s where user_id = %s",
                    (
                        user.name,
                        str(user.email),
                        user.organization,
                        user.password_hash,
                        Jsonb(dict(user.preferences)),
                        str(user.pending_email) if user.pending_email else None,
                        user.email_verified_at,
                        now,
                        user.user_id,
                    ),
                )
        except errors.UniqueViolation as error:
            raise EmailAlreadyUsedError(str(user.email)) from error

    def set_avatar(
        self, user_id: UUID, key: str | None, media_type: str | None, now: datetime
    ) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update identity.users set avatar_key = %s, avatar_type = %s, "
                "avatar_updated_at = %s, updated_at = %s where user_id = %s",
                (key, media_type, now if key else None, now, user_id),
            )


class PostgisSessionStore:
    def __init__(self, pool: ConnectionPool, days: int = SESSION_DAYS) -> None:
        self._pool = pool
        self._days = days

    def create(self, user_id: UUID) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        with self._pool.connection() as conn:
            conn.execute(
                "insert into identity.sessions (token_hash, user_id, created_at, expires_at) "
                "values (%s, %s, %s, %s)",
                (_token_hash(token), user_id, now, now + timedelta(days=self._days)),
            )
        return token

    def user_for(self, token: str) -> UUID | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select user_id from identity.sessions "
                "where token_hash = %s and expires_at > now()",
                (_token_hash(token),),
            ).fetchone()
        return row[0] if row else None

    def revoke(self, token: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "delete from identity.sessions where token_hash = %s", (_token_hash(token),)
            )

    def revoke_all(self, user_id: UUID) -> int:
        with self._pool.connection() as conn:
            cursor = conn.execute("delete from identity.sessions where user_id = %s", (user_id,))
            return cursor.rowcount


class PostgisTokenStore:
    """Links de e-mail: só o sha256 do token fica gravado; cada link vale uma vez."""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def issue(
        self,
        user_id: UUID,
        purpose: TokenPurpose,
        *,
        now: datetime,
        ttl: timedelta,
        new_email: EmailAddress | None = None,
    ) -> str:
        token = secrets.token_urlsafe(32)
        with self._pool.connection() as conn, conn.transaction():
            # um link novo invalida os anteriores do mesmo tipo
            conn.execute(
                "update identity.email_tokens set used_at = %s "
                "where user_id = %s and purpose = %s and used_at is null",
                (now, user_id, purpose.value),
            )
            conn.execute(
                "insert into identity.email_tokens (token_hash, user_id, purpose, new_email, "
                "created_at, expires_at) values (%s, %s, %s, %s, %s, %s)",
                (
                    _token_hash(token),
                    user_id,
                    purpose.value,
                    str(new_email) if new_email else None,
                    now,
                    now + ttl,
                ),
            )
        return token

    def consume(
        self, token: str, purposes: tuple[TokenPurpose, ...], now: datetime
    ) -> EmailToken | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "update identity.email_tokens set used_at = %s "
                "where token_hash = %s and used_at is null and expires_at > %s "
                "and purpose = any(%s) returning user_id, purpose, new_email, created_at",
                (now, _token_hash(token), now, [p.value for p in purposes]),
            ).fetchone()
        if row is None:
            return None
        return EmailToken(
            user_id=row[0],
            purpose=TokenPurpose(row[1]),
            new_email=EmailAddress(row[2]) if row[2] else None,
            created_at=row[3],
        )

    def last_issued(self, user_id: UUID, purpose: TokenPurpose) -> datetime | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "select max(created_at) from identity.email_tokens "
                "where user_id = %s and purpose = %s",
                (user_id, purpose.value),
            ).fetchone()
        return row[0] if row else None
