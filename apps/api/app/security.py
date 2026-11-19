from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.config import get_settings

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(subject: str, papel: str) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expires_minutes)
    payload = {"sub": subject, "papel": papel, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])


# --- state do OAuth das caixas de envio (ADR 0016) ---
# JWT curto e descartável, separado do token de sessão: evita CSRF no callback do Google sem precisar
# de uma tabela de sessão nova, e a `finalidade` impede reaproveitar um access_token comum como state.

FINALIDADE_OAUTH_CAIXA = "conectar_caixa_envio"


def criar_state_oauth(admin_id: str) -> str:
    settings = get_settings()
    expira = datetime.now(UTC) + timedelta(minutes=10)
    payload = {"sub": admin_id, "finalidade": FINALIDADE_OAUTH_CAIXA, "exp": expira}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def validar_state_oauth(state: str) -> str:
    """Devolve o id do admin que iniciou a conexão, ou levanta `jwt.PyJWTError`/`KeyError`/`ValueError`."""
    payload = jwt.decode(state, get_settings().jwt_secret, algorithms=[ALGORITHM])
    if payload.get("finalidade") != FINALIDADE_OAUTH_CAIXA:
        raise ValueError("state não é de uma conexão de caixa de envio.")
    return payload["sub"]
