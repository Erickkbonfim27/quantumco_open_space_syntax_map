from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg import errors
from psycopg_pool import ConnectionPool

from quantumco.identity.application.ports import EmailAlreadyUsedError
from quantumco.identity.domain.email import EmailAddress
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
                "select user_id, name, email, organization, password_hash, created_at "
                f"from identity.users where {where} = %s",
                (value,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], EmailAddress(row[2]), row[3], row[4], row[5])

    def by_email(self, email: EmailAddress) -> User | None:
        return self._one("email", str(email))

    def by_id(self, user_id: UUID) -> User | None:
        return self._one("user_id", user_id)


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
