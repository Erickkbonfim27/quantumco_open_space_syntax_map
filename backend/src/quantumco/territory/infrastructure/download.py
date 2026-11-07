"""Download com cache local, novas tentativas e log de progresso (arquivos de 10–80 MB do IBGE)."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)

USER_AGENT = "quantumco/1.0 (mapa sintatico aberto; +https://quantumco.com.br)"
RETRIES = 4


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(timeout, connect=20), follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )  # fmt: skip


def fetch_file(
    url: str, cache_dir: Path, *, max_age_days: float = 30, timeout: float = 120
) -> Path:
    """Baixa `url` para o cache (uma vez a cada `max_age_days`) e devolve o caminho local."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    name = url.rstrip("/").rsplit("/", 1)[-1].split("?")[0] or "download"
    target = cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()[:10]}-{name}"
    if target.exists() and (time.time() - target.stat().st_mtime) < max_age_days * 86400:
        log.info("  cache: %s (%.1f MB)", target.name, target.stat().st_size / 1e6)
        return target
    partial = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, RETRIES + 1):
        try:
            started = time.perf_counter()
            with _client(timeout) as client, client.stream("GET", url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or 0)
                done, next_log = 0, 0.25
                with partial.open("wb") as out:
                    for chunk in response.iter_bytes(1 << 20):
                        out.write(chunk)
                        done += len(chunk)
                        if total and done / total >= next_log:
                            log.info(
                                "  %s: %d%% de %.1f MB", name, 100 * done // total, total / 1e6
                            )
                            next_log += 0.25
            partial.replace(target)
            log.info(
                "  baixado %s (%.1f MB em %.1fs)",
                name, target.stat().st_size / 1e6, time.perf_counter() - started,
            )  # fmt: skip
            return target
        except (httpx.HTTPError, OSError) as exc:
            wait = 2**attempt
            log.warning("  falha ao baixar %s (tentativa %d/%d): %s; de novo em %ds",
                        name, attempt, RETRIES, exc, wait)  # fmt: skip
            if attempt == RETRIES:
                raise
            time.sleep(wait)
    raise RuntimeError("inalcançável")


def get_json(url: str, *, params: dict[str, Any] | None = None, timeout: float = 120) -> Any:
    """GET de JSON com novas tentativas (APIs do SGB e do Ministério da Saúde oscilam)."""
    for attempt in range(1, RETRIES + 1):
        try:
            with _client(timeout) as client:
                response = client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            wait = 2**attempt
            log.warning("  falha em %s (tentativa %d/%d): %s; de novo em %ds",
                        url, attempt, RETRIES, exc, wait)  # fmt: skip
            if attempt == RETRIES:
                raise
            time.sleep(wait)
    raise RuntimeError("inalcançável")


def get_text(url: str, *, timeout: float = 60) -> str:
    """GET de texto (listagem de pasta do FTP do IBGE) com novas tentativas."""
    for attempt in range(1, RETRIES + 1):
        try:
            with _client(timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except httpx.HTTPError as exc:
            wait = 2**attempt
            log.warning("  falha em %s (tentativa %d/%d): %s; de novo em %ds",
                        url, attempt, RETRIES, exc, wait)  # fmt: skip
            if attempt == RETRIES:
                raise
            time.sleep(wait)
    raise RuntimeError("inalcançável")
