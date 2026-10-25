"""Prints das páginas auditadas no MinIO (CONSTITUICAO §16.1). Bucket privado."""

import asyncio
import io
import logging
from typing import Protocol
from urllib.parse import urlsplit

log = logging.getLogger("slp_workers.artefatos")


class Armazenamento(Protocol):
    async def salvar_png(self, chave: str, dados: bytes) -> str | None: ...


class ArmazenamentoMinio:
    def __init__(self, endpoint: str, usuario: str, senha: str, bucket: str) -> None:
        from minio import Minio

        partes = urlsplit(endpoint)
        self._bucket = bucket
        self._cliente = Minio(
            partes.netloc, access_key=usuario, secret_key=senha, secure=partes.scheme == "https"
        )
        self._bucket_ok = False

    def _salvar(self, chave: str, dados: bytes) -> str:
        if not self._bucket_ok:
            if not self._cliente.bucket_exists(self._bucket):
                self._cliente.make_bucket(self._bucket)
            self._bucket_ok = True
        self._cliente.put_object(self._bucket, chave, io.BytesIO(dados), len(dados), content_type="image/png")
        return f"s3://{self._bucket}/{chave}"

    async def salvar_png(self, chave: str, dados: bytes) -> str | None:
        """Falha ao salvar print não derruba a auditoria: o resultado dos testes vale mais que a imagem."""
        try:
            return await asyncio.to_thread(self._salvar, chave, dados)
        except Exception as exc:  # noqa: BLE001
            log.warning("print não salvo (%s): %s", chave, exc)
            return None


class ArmazenamentoMemoria:
    """Para testes."""

    def __init__(self) -> None:
        self.arquivos: dict[str, bytes] = {}

    async def salvar_png(self, chave: str, dados: bytes) -> str | None:
        self.arquivos[chave] = dados
        return f"s3://teste/{chave}"
