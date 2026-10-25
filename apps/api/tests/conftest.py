import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Papel, Usuario  # noqa: E402
from app.security import hash_password  # noqa: E402

engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                       poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def db():
    Base.metadata.create_all(engine)
    session = TestingSession()
    app.dependency_overrides[get_db] = lambda: session
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin(db):
    user = Usuario(nome="Admin", email="admin@exemplo.com", senha_hash=hash_password("senha-muito-forte"),
                   papel=Papel.admin)
    db.add(user)
    db.commit()
    return user


class FilaFalsa:
    """Substitui o arq nos testes: registra os envios e imita o job_id único por empresa."""

    def __init__(self):
        self.enviados: list = []
        self.indisponivel = False

    async def enfileirar_processamento(self, empresa_id):
        from app.queue import FilaIndisponivel

        if self.indisponivel:
            raise FilaIndisponivel("redis fora do ar")
        if empresa_id in self.enviados:
            return False
        self.enviados.append(empresa_id)
        return True


@pytest.fixture
def fila():
    from app.queue import get_fila

    falsa = FilaFalsa()
    app.dependency_overrides[get_fila] = lambda: falsa
    return falsa


def _criar_usuario(db, email, papel):
    user = Usuario(nome=email.split("@")[0], email=email, senha_hash=hash_password("senha-muito-forte"),
                   papel=papel)
    db.add(user)
    db.commit()
    return user


def _token(client, email):
    r = client.post("/auth/login", data={"username": email, "password": "senha-muito-forte"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def vendedor_headers(client, db):
    _criar_usuario(db, "vendedor@exemplo.com", Papel.vendedor)
    return _token(client, "vendedor@exemplo.com")


@pytest.fixture
def leitura_headers(client, db):
    _criar_usuario(db, "leitura@exemplo.com", Papel.leitura)
    return _token(client, "leitura@exemplo.com")
