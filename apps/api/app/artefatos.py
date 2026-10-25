"""Leitura dos arquivos privados guardados pelos workers no MinIO (prints e mini-relatórios).

Nada é público: as rotas que usam este módulo exigem login, e os endereços s3:// nunca saem pela API.
"""

from functools import lru_cache
from typing import Protocol
from urllib.parse import urlsplit

from app.config import get_settings


class Armazenamento(Protocol):
    def ler(self, chave: str) -> bytes | None: ...

    def existe(self, chave: str) -> bool: ...


class ArmazenamentoMinio:
    def __init__(self) -> None:
        from minio import Minio

        s = get_settings()
        partes = urlsplit(s.minio_endpoint)
        self.bucket = s.minio_bucket
        self._cliente = Minio(
            partes.netloc,
            access_key=s.minio_root_user,
            secret_key=s.minio_root_password,
            secure=partes.scheme == "https",
        )

    def existe(self, chave: str) -> bool:
        try:
            self._cliente.stat_object(self.bucket, chave)
            return True
        except Exception:  # noqa: BLE001
            return False

    def ler(self, chave: str) -> bytes | None:
        try:
            resposta = self._cliente.get_object(self.bucket, chave)
        except Exception:  # noqa: BLE001 — inexistente ou MinIO fora: a rota responde 404
            return None
        try:
            return resposta.read()
        finally:
            resposta.close()
            resposta.release_conn()


def chave_de(url_s3: str | None) -> str | None:
    """s3://<bucket>/<chave> → <chave>, só para o bucket configurado."""
    prefixo = f"s3://{get_settings().minio_bucket}/"
    return url_s3[len(prefixo) :] if url_s3 and url_s3.startswith(prefixo) else None


def chave_relatorio(empresa_id: object, auditoria_id: object, extensao: str) -> str:
    """Mesmo caminho usado pelo worker (slp_workers/orchestrator/relatorio.py)."""
    return f"relatorios/{empresa_id}/{auditoria_id}.{extensao}"


@lru_cache
def _minio() -> ArmazenamentoMinio:
    return ArmazenamentoMinio()


def get_armazenamento() -> Armazenamento:
    return _minio()
