"""Arquivos oficiais do CNPJ: compartilhamento público da Receita no Nextcloud, via WebDAV.

Página: https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9 (o caminho antigo
`/dados/cnpj/dados_abertos_cnpj/` passou a responder 404). No WebDAV público do Nextcloud o
usuário é o token do compartilhamento e a senha é vazia.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Sequence
from pathlib import Path

import httpx

from quantumco.datasets.application.ports import RemoteFile

log = logging.getLogger(__name__)

BASE = "https://arquivos.receitafederal.gov.br/public.php/webdav"
SHARE = "YggdBLfdninEJX9"
USER_AGENT = "quantumco/1.0 (dados abertos; +https://quantumco.com.br)"
RETRIES = 6
_RESPONSE = re.compile(r"<d:response>(.*?)</d:response>", re.S)


def parse_listing(xml: str) -> list[RemoteFile | str]:
    """Resposta PROPFIND → arquivos (com tamanho) e pastas (nome com '/')."""
    found: list[RemoteFile | str] = []
    for block in _RESPONSE.findall(xml):
        href = re.search(r"<d:href>(.*?)</d:href>", block)
        if not href:
            continue
        name = href.group(1).rstrip("/").rsplit("/", 1)[-1]
        size = re.search(r"<d:getcontentlength>(\d+)</d:getcontentlength>", block)
        if size:
            found.append(RemoteFile(name, int(size.group(1))))
        elif "<d:collection/>" in block:
            found.append(f"{name}/")
    return found


class ReceitaWebdav:
    def __init__(self, base: str = BASE, share: str = SHARE) -> None:
        self._base = base.rstrip("/")
        self._auth = (share, "")

    def _client(self, timeout: httpx.Timeout | float) -> httpx.Client:
        return httpx.Client(
            auth=self._auth, timeout=timeout, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )  # fmt: skip

    def _list(self, path: str) -> list[RemoteFile | str]:
        for attempt in range(1, RETRIES + 1):
            try:
                with self._client(60) as client:
                    response = client.request(
                        "PROPFIND", f"{self._base}/{path}", headers={"Depth": "1"}
                    )
                response.raise_for_status()
                return parse_listing(response.text)
            except httpx.HTTPError as exc:
                if attempt == RETRIES:
                    raise
                log.warning("Receita: falha ao listar %s (%d/%d): %s", path, attempt, RETRIES, exc)
                time.sleep(2**attempt)
        raise RuntimeError("inalcançável")

    def competencias(self) -> Sequence[str]:
        return [str(x).rstrip("/") for x in self._list("") if isinstance(x, str)]

    def files(self, competencia: str) -> Sequence[RemoteFile]:
        return [x for x in self._list(f"{competencia}/") if isinstance(x, RemoteFile)]

    def download(self, competencia: str, name: str, target: Path) -> int:
        """Baixa com retomada (Range): uma queda no meio de 2 GB não recomeça do zero."""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        url = f"{self._base}/{competencia}/{name}"
        for attempt in range(1, RETRIES + 1):
            done = target.stat().st_size if target.exists() else 0
            headers = {"Range": f"bytes={done}-"} if done else {}
            try:
                started, next_log = time.perf_counter(), 0.0
                with (
                    self._client(httpx.Timeout(120, connect=30)) as client,
                    client.stream("GET", url, headers=headers) as response,
                ):
                    if done and response.status_code != 206:  # servidor ignorou o Range
                        done = 0
                        target.unlink(missing_ok=True)
                    response.raise_for_status()
                    total = done + int(response.headers.get("content-length") or 0)
                    with target.open("ab") as out:
                        for chunk in response.iter_bytes(4 << 20):
                            out.write(chunk)
                            done += len(chunk)
                            if total and done / total >= next_log:
                                rate = done / max(time.perf_counter() - started, 1e-6) / 1e6
                                log.info("  %s: %d%% (%.0f MB/s)", name, 100 * done // total, rate)
                                next_log += 0.2
                return target.stat().st_size
            except (httpx.HTTPError, OSError) as exc:
                if attempt == RETRIES:
                    raise
                wait = 2**attempt
                log.warning("Receita: falha em %s (%d/%d): %s; retomando em %ds",
                            name, attempt, RETRIES, exc, wait)  # fmt: skip
                time.sleep(wait)
        raise RuntimeError("inalcançável")
