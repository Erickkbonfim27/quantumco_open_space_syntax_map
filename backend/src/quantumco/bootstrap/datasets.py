"""Montagem do contexto `datasets` (dados nacionais: Receita → RustFS → ClickHouse)."""

from __future__ import annotations

import os
from pathlib import Path

from quantumco.bootstrap.settings import Settings
from quantumco.datasets.application.ingest_cnpj import IngestCnpj
from quantumco.datasets.infrastructure.clickhouse_warehouse import ClickHouseWarehouse
from quantumco.datasets.infrastructure.receita_webdav import ReceitaWebdav
from quantumco.datasets.infrastructure.s3_raw import S3RawStore
from quantumco.platform.clickhouse import ClickHouse

DATA_QUEUE = "dados"


def clickhouse(settings: Settings) -> ClickHouse:
    if not settings.clickhouse_url:
        raise RuntimeError(
            "QC_CLICKHOUSE_URL não definido (http://usuario:senha@clickhouse:8123/dados)"
        )
    return ClickHouse(settings.clickhouse_url)


def ingest_cnpj_use_case(settings: Settings) -> IngestCnpj:
    # trava: os arquivos da Receita (GBs) só podem ser baixados no servidor, nunca numa máquina
    # de desenvolvimento; QC_ALLOW_RECEITA_DOWNLOAD=1 existe só no serviço worker-dados da VPS
    if os.environ.get("QC_ALLOW_RECEITA_DOWNLOAD") != "1":
        raise RuntimeError(
            "download da Receita bloqueado aqui: rode na VPS (serviço worker-dados) ou use "
            "`quantumco dados cnpj --enfileirar`"
        )
    if not settings.s3_configured:
        raise RuntimeError("QC_S3_* não definidos: o bruto da Receita fica no RustFS")
    scratch_dir: Path = settings.cache_dir / "datasets"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    return IngestCnpj(
        receita=ReceitaWebdav(),
        raw=S3RawStore(
            endpoint=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            bucket=settings.s3_bucket_dados,
        ),
        warehouse=ClickHouseWarehouse(clickhouse(settings)),
        scratch=lambda name: scratch_dir / name,
    )
