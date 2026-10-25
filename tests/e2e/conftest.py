"""Fluxo API → fila → worker com Postgres e Redis reais (job `fluxo` do CI).

Rode com o banco migrado (`alembic upgrade head`) e:
    FLOW_TESTS=1 PYTHONPATH=apps/api:workers pytest tests/e2e
"""

import os
import uuid

import pytest

collect_ignore_glob = [] if os.getenv("FLOW_TESTS") else ["test_*.py"]

SENHA = "senha-muito-forte"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def headers(client):
    from app.db import SessionLocal
    from app.models import Papel, Usuario
    from app.security import hash_password

    email = f"fluxo-{uuid.uuid4().hex[:8]}@exemplo.com"
    with SessionLocal() as db:
        db.add(Usuario(nome="Fluxo", email=email, senha_hash=hash_password(SENHA), papel=Papel.vendedor))
        db.commit()
    r = client.post("/auth/login", data={"username": email, "password": SENHA})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
