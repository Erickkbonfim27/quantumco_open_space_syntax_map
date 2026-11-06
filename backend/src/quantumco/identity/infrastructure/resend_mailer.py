"""Adaptador `Mailer` via API HTTP do Resend (https://resend.com/docs/api-reference)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from quantumco.identity.application.ports import MailDeliveryError
from quantumco.identity.domain.email import EmailMessage, Sender

API_URL = "https://api.resend.com"
_RETRYABLE = frozenset({429, 500, 502, 503, 504})

log = logging.getLogger(__name__)


class MailerError(MailDeliveryError):
    pass


class RestrictedApiKeyError(MailerError):
    """A chave só tem permissão de envio (o recomendado em produção)."""


class ResendMailer:
    def __init__(
        self,
        *,
        api_key: str,
        sender: Sender,
        client: httpx.Client | None = None,
        max_attempts: int = 3,
        initial_backoff_s: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("RESEND_API_KEY vazio")
        self._sender = sender
        self._client = client or httpx.Client(base_url=API_URL, timeout=20.0)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._max_attempts = max_attempts
        self._initial_backoff_s = initial_backoff_s
        self._sleep = sleep

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        delay = self._initial_backoff_s
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.request(method, path, json=json, headers=self._headers)
            except httpx.HTTPError as error:
                if attempt == self._max_attempts:
                    raise MailerError(f"Resend inacessível: {type(error).__name__}") from error
                self._sleep(delay)
                delay *= 2
                continue
            if response.status_code not in _RETRYABLE or attempt == self._max_attempts:
                break
            log.warning(
                "Resend %s %s: HTTP %d; nova tentativa em %.0fs",
                method,
                path,
                response.status_code,
                delay,
            )
            self._sleep(delay)
            delay *= 2
        if response.status_code == 401 and "restricted_api_key" in response.text:
            raise RestrictedApiKeyError("chave do Resend só tem permissão de envio")
        if response.status_code >= 400:
            # a resposta do Resend traz {"name", "message"}; nunca logamos a chave
            raise MailerError(f"Resend HTTP {response.status_code}: {response.text[:300]}")
        return response.json()

    def send(self, message: EmailMessage) -> str:
        payload: dict[str, Any] = {
            "from": self._sender.formatted(),
            "to": [str(address) for address in message.to],
            "subject": message.subject,
            "text": message.text,
        }
        if message.html:
            payload["html"] = message.html
        data = self._request("POST", "/emails", payload)
        message_id = str(data.get("id", ""))
        log.info("e-mail enviado via Resend: %s → %d destinatário(s)", message_id, len(message.to))
        return message_id

    def domain_status(self, domain: str) -> str | None:
        """Status de verificação do domínio remetente no Resend (None se não cadastrado)."""
        data = self._request("GET", "/domains")
        for item in data.get("data", []):
            if item.get("name") == domain:
                return str(item.get("status"))
        return None
