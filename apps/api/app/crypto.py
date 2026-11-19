"""Criptografia em repouso de campos sensíveis (CONSTITUICAO §15.1).

Hoje só o `refresh_token_criptografado` das caixas de envio conectadas (ADR 0016) passa por aqui — nenhum
outro dado sensível do projeto precisa disso ainda (senhas usam bcrypt, que é hash, não criptografia
reversível; aqui precisamos recuperar o token original para chamar a Gmail API).
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class ErroCriptografia(Exception):
    pass


@lru_cache
def _fernet() -> Fernet:
    chave = get_settings().field_encryption_key
    if not chave:
        raise ErroCriptografia("FIELD_ENCRYPTION_KEY não configurada — gere uma com Fernet.generate_key().")
    try:
        return Fernet(chave.encode())
    except ValueError as e:
        raise ErroCriptografia("FIELD_ENCRYPTION_KEY inválida.") from e


def criptografar(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def descriptografar(texto: str) -> str:
    try:
        return _fernet().decrypt(texto.encode()).decode()
    except InvalidToken as e:
        raise ErroCriptografia(
            "Não foi possível descriptografar — chave incorreta ou dado corrompido."
        ) from e
