"""Fotos de perfil no RustFS (compatível com S3), via cliente MinIO.

O MinIO é leve (sem o botocore) e fala com qualquer S3 compatível; usa endereçamento por
caminho (`https://host/bucket/chave`) com servidores que não são da AWS, como o RustFS.
O bucket é privado: a API busca o arquivo e o entrega ao navegador do dono.
Qualquer falha do servidor (fora do ar, sem espaço, credencial errada) vira
`AvatarStorageUnavailableError`, que a API responde como 503.
"""

from __future__ import annotations

import io
import logging
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager, Retry, Timeout
from urllib3.exceptions import HTTPError as Urllib3Error

from quantumco.identity.application.ports import AvatarStorageUnavailableError

log = logging.getLogger(__name__)


class S3AvatarStore:
    def __init__(
        self, *, endpoint: str, access_key: str, secret_key: str, region: str, bucket: str
    ) -> None:
        url = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
        if not url.hostname:
            raise ValueError("QC_S3_ENDPOINT inválido")
        host = f"{url.hostname}:{url.port}" if url.port else url.hostname
        # poucas tentativas e prazo curto: a API não pode ficar presa num armazenamento lento
        http = PoolManager(
            timeout=Timeout(connect=5, read=20),
            retries=Retry(total=2, backoff_factor=0.3, status_forcelist=(502, 503, 504)),
        )
        self._client = Minio(
            host,
            access_key=access_key,
            secret_key=secret_key,
            region=region or None,
            secure=url.scheme == "https",
            http_client=http,
        )
        self._bucket = bucket
        self._ready = False

    def _ensure_bucket(self) -> None:
        if self._ready:
            return
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                log.info("bucket %s criado no armazenamento de arquivos", self._bucket)
        except (S3Error, OSError, Urllib3Error) as error:
            raise AvatarStorageUnavailableError(str(error)) from error
        self._ready = True

    def put(self, key: str, content: bytes, media_type: str) -> None:
        self._ensure_bucket()
        try:
            self._client.put_object(
                self._bucket, key, io.BytesIO(content), len(content), content_type=media_type
            )
        except (S3Error, OSError, Urllib3Error) as error:
            raise AvatarStorageUnavailableError(str(error)) from error

    def get(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(self._bucket, key)
        except S3Error as error:
            if error.code in ("NoSuchKey", "NoSuchBucket"):
                return None
            raise AvatarStorageUnavailableError(str(error)) from error
        except (OSError, Urllib3Error) as error:
            raise AvatarStorageUnavailableError(str(error)) from error
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, key: str) -> None:
        try:
            self._client.remove_object(self._bucket, key)
        except (S3Error, OSError, Urllib3Error) as error:
            raise AvatarStorageUnavailableError(str(error)) from error
