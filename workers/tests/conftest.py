import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import uuid  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from slp_workers.db import empresas, metadata  # noqa: E402


@pytest.fixture
def engine():
    eng = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
                        poolclass=StaticPool)
    metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def empresa_id(engine):
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(empresas.insert().values(id=eid, nome="exemplo.com.br", dominio="exemplo.com.br",
                                              estado="NOVO"))
    return eid
