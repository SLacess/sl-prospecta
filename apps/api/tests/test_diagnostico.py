"""Relatório público do diagnóstico (CONSTITUICAO §9.1, §17, §21.1) — o link que acompanha o e-mail."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.artefatos import chave_relatorio, get_armazenamento
from app.main import app
from app.models import Auditoria, Empresa, EstadoProspect, Microsite


class ArmazenamentoFalso:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}

    def ler(self, chave):
        return self.arquivos.get(chave)

    def existe(self, chave):
        return chave in self.arquivos


@pytest.fixture
def armazenamento():
    falso = ArmazenamentoFalso()
    app.dependency_overrides[get_armazenamento] = lambda: falso
    yield falso
    app.dependency_overrides.pop(get_armazenamento, None)


def _microsite(db, armazenamento, *, expirado=False, com_relatorio=True) -> str:
    empresa = Empresa(nome="Hospital Exemplo", dominio="hospital-exemplo.com.br", fonte="manual",
                       estado=EstadoProspect.em_sequencia)
    db.add(empresa)
    db.flush()
    auditoria = Auditoria(empresa_id=empresa.id, nota=62)
    db.add(auditoria)
    db.flush()
    slug = "slug-de-teste-" + uuid.uuid4().hex[:8]
    db.add(Microsite(
        empresa_id=empresa.id, auditoria_id=auditoria.id, slug=slug,
        expira_em=datetime.now(UTC) + (timedelta(days=-1) if expirado else timedelta(days=120)),
    ))
    db.commit()
    if com_relatorio:
        chave = chave_relatorio(empresa.id, auditoria.id, "html")
        armazenamento.arquivos[chave] = "<html><body>Relatório de acessibilidade</body></html>".encode()
    return slug


def test_diagnostico_nao_exige_login(client, db, armazenamento):
    slug = _microsite(db, armazenamento)
    r = client.get(f"/diagnostico/{slug}")
    assert r.status_code == 200
    assert "Relatório de acessibilidade" in r.text
    assert r.headers["content-type"].startswith("text/html")


def test_slug_inexistente_e_404(client, armazenamento):
    r = client.get("/diagnostico/nao-existe")
    assert r.status_code == 404


def test_slug_expirado_e_404(client, db, armazenamento):
    slug = _microsite(db, armazenamento, expirado=True)
    r = client.get(f"/diagnostico/{slug}")
    assert r.status_code == 404


def test_sem_html_no_armazenamento_e_404(client, db, armazenamento):
    slug = _microsite(db, armazenamento, com_relatorio=False)
    r = client.get(f"/diagnostico/{slug}")
    assert r.status_code == 404
