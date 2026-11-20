"""Descriptografia do refresh_token das caixas de envio (CONSTITUICAO §15.1; ADR 0016).

Mesma chave e mesmo algoritmo do `app/crypto.py` da API (Fernet) — é a API que criptografa ao conectar
uma caixa; só o worker precisa descriptografar, para chamar a Gmail API na hora de enviar (Tarefa 3).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from slp_workers.settings import get_config


class ErroCriptografia(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    chave = get_config().field_encryption_key
    if not chave:
        raise ErroCriptografia("FIELD_ENCRYPTION_KEY não configurada.")
    try:
        return Fernet(chave.encode())
    except ValueError as e:
        raise ErroCriptografia("FIELD_ENCRYPTION_KEY inválida.") from e


def descriptografar(texto: str) -> str:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken as e:
        raise ErroCriptografia(
            "Não foi possível descriptografar o refresh_token — chave incorreta ou dado corrompido."
        ) from e
