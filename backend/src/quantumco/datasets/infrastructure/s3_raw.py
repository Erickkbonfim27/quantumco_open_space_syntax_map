"""Bruto no RustFS (S3): os ZIPs da fonte, exatamente como vieram. Bucket privado."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error

log = logging.getLogger(__name__)

PART_SIZE = 64 * 1024 * 1024  # envio em partes de 64 MB (arquivos de até ~2,3 GB)


class S3RawStore:
    def __init__(
        self, *, endpoint: str, access_key: str, secret_key: str, region: str, bucket: str
    ) -> None:
        url = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
        if not url.hostname:
            raise ValueError("QC_S3_ENDPOINT inválido")
        host = f"{url.hostname}:{url.port}" if url.port else url.hostname
        self._client = Minio(
            host, access_key=access_key, secret_key=secret_key, region=region or None,
            secure=url.scheme == "https",
        )  # fmt: skip
        self._bucket = bucket
        self._ready = False

    def _ensure_bucket(self) -> None:
        if not self._ready:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                log.info("bucket %s criado no RustFS", self._bucket)
            self._ready = True

    def size(self, key: str) -> int | None:
        self._ensure_bucket()
        try:
            return int(self._client.stat_object(self._bucket, key).size or 0)
        except S3Error as error:
            if error.code in {"NoSuchKey", "NoSuchObject", "NotFound"}:
                return None
            raise

    def put(self, key: str, path: Path) -> None:
        self._ensure_bucket()
        self._client.fput_object(self._bucket, key, str(path), part_size=PART_SIZE)

    def get(self, key: str, target: Path) -> None:
        self._ensure_bucket()
        target.parent.mkdir(parents=True, exist_ok=True)
        self._client.fget_object(self._bucket, key, str(target))
