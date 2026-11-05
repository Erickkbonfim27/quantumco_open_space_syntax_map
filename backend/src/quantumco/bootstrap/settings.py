"""Configuração lida do ambiente (e do `.env` na raiz do repositório, se existir).

Só as variáveis que o código já usa estão aqui. A lista completa, incluindo a infra da VPS,
está em `.env.example`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[4]  # onde fica o .env local
BACKEND_ROOT = Path(__file__).resolve().parents[3]  # build path "/backend" no deploy


def load_env_file(path: Path = REPO_ROOT / ".env") -> None:
    """Carrega o `.env` sem sobrescrever variáveis já definidas no ambiente."""
    if path.is_file():
        load_dotenv(path, override=False)


def _path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else BACKEND_ROOT / path


@dataclass(frozen=True, slots=True)
class Settings:
    methodology_dir: Path
    overpass_url: str
    overpass_timeout_s: float
    log_level: str
    resend_api_key: str
    mail_from: str
    mail_from_name: str
    owner_email: str
    cors_origins: tuple[str, ...]
    database_url: str
    cookie_secure: bool
    cache_dir: Path = BACKEND_ROOT / ".cache"

    def require_database(self) -> str:
        if not self.database_url:
            raise RuntimeError(
                "QC_DATABASE_URL não definido: rede e análise ficam só no PostGIS da VPS"
            )
        return self.database_url

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        source = os.environ if env is None else env
        return cls(
            methodology_dir=_path(source.get("QC_METHODOLOGY_DIR", "methodology/v1")),
            overpass_url=source.get("QC_OVERPASS_URL", "https://overpass-api.de/api/interpreter"),
            overpass_timeout_s=float(source.get("QC_OVERPASS_TIMEOUT_S", "300")),
            log_level=source.get("QC_LOG_LEVEL", "INFO").upper(),
            resend_api_key=source.get("RESEND_API_KEY", "").strip(),
            mail_from=source.get("MAIL_FROM", "spacesyntax@erickkbonfim.com.br").strip(),
            mail_from_name=source.get("MAIL_FROM_NAME", "quantumco").strip(),
            owner_email=source.get("OWNER_EMAIL", "").strip(),
            database_url=source.get("QC_DATABASE_URL", "").strip(),
            cookie_secure=source.get("QC_COOKIE_SECURE", "true").strip().lower() != "false",
            cache_dir=_path(source.get("QC_CACHE_DIR", ".cache")),
            cors_origins=tuple(
                origin.strip()
                for origin in source.get("QC_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
        )
