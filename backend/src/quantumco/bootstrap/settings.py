"""Configuração lida do ambiente (e do `.env` na raiz do repositório, se existir).

Só as variáveis que o código já usa estão aqui. A lista completa, incluindo a infra da VPS,
está em `.env.example`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[4]  # onde fica o .env local
BACKEND_ROOT = Path(__file__).resolve().parents[3]  # build path "/backend" no deploy


_FROM_FILE = "_QC_FROM_DOTENV"  # nomes das variáveis que vieram do .env (não do ambiente real)


def load_env_file(path: Path = REPO_ROOT / ".env") -> None:
    """Carrega o `.env` sem sobrescrever variáveis definidas no ambiente de verdade.

    Variáveis que vieram do próprio `.env` são relidas a cada carga: com `serve --reload`, o
    processo pai lê o arquivo uma vez e os filhos herdam o ambiente; sem isto, uma mudança no
    `.env` (ex.: MAIL_FROM) só valeria depois de reiniciar a API por completo.
    """
    if not path.is_file():
        return
    from_file = {k for k in os.environ.get(_FROM_FILE, "").split(",") if k}
    for key, value in dotenv_values(path).items():
        if value is None:
            continue
        if key not in os.environ or key in from_file:
            os.environ[key] = value
            from_file.add(key)
    os.environ[_FROM_FILE] = ",".join(sorted(from_file))


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
    # fila de cálculo dos cenários (Redis + RQ) e seus limites (Q45)
    redis_url: str = ""
    workers: int = 2
    scenario_timeout_s: int = 3600
    scenario_daily_quota: int = 10
    scenario_queue_max: int = 20
    scenario_active_per_user: int = 2
    # links dos e-mails da conta (QC_PUBLIC_BASE_URL) e fotos de perfil no RustFS (S3)
    public_base_url: str = "https://quantumco.com.br"
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_avatars: str = "quantumco-avatars"

    @property
    def s3_configured(self) -> bool:
        return bool(self.s3_endpoint and self.s3_access_key and self.s3_secret_key)

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
            mail_from=source.get("MAIL_FROM", "noreply@quantumco.com.br").strip(),
            mail_from_name=source.get("MAIL_FROM_NAME", "quantumco").strip(),
            owner_email=source.get("OWNER_EMAIL", "").strip(),
            database_url=source.get("QC_DATABASE_URL", "").strip(),
            cookie_secure=source.get("QC_COOKIE_SECURE", "true").strip().lower() != "false",
            cache_dir=_path(source.get("QC_CACHE_DIR", ".cache")),
            redis_url=source.get("QC_REDIS_URL", "").strip(),
            workers=max(1, min(8, int(source.get("QC_WORKERS", "2")))),
            scenario_timeout_s=int(source.get("QC_SCENARIO_TIMEOUT_S", "3600")),
            scenario_daily_quota=int(source.get("QC_SCENARIO_DAILY_QUOTA", "10")),
            scenario_queue_max=int(source.get("QC_SCENARIO_QUEUE_MAX", "20")),
            scenario_active_per_user=int(source.get("QC_SCENARIO_ACTIVE_PER_USER", "2")),
            public_base_url=(
                source.get("QC_PUBLIC_BASE_URL", "").strip().rstrip("/")
                or "https://quantumco.com.br"
            ),
            s3_endpoint=source.get("QC_S3_ENDPOINT", "").strip(),
            s3_region=source.get("QC_S3_REGION", "").strip(),
            s3_access_key=source.get("QC_S3_ACCESS_KEY", "").strip(),
            s3_secret_key=source.get("QC_S3_SECRET_KEY", "").strip(),
            s3_bucket_avatars=(
                source.get("QC_S3_BUCKET_AVATARS", "").strip() or "quantumco-avatars"
            ),
            cors_origins=tuple(
                origin.strip()
                for origin in source.get("QC_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
        )
