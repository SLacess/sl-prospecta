"""Fase 2, Tarefa 1: qualificação na Ficha e pesos/faixas do score (só o admin altera)."""

import pytest

from app.models import Config, Empresa, EstadoProspect, Evento, Qualificacao
from tests.conftest import _token

PESOS = {
    "fit_icp": 0.30,
    "intencao": 0.25,
    "gravidade_barreiras": 0.20,
    "pressao_regulatoria": 0.15,
    "acessibilidade_decisor": 0.10,
}
COMPONENTES = [
    {"chave": "fit_icp", "rotulo": "Aderência ao perfil de cliente (ICP)", "valor": 90, "peso": 0.3,
     "contribuicao": 27.0, "justificativa": "Setor prioritário (saúde)."},
    {"chave": "acessibilidade_decisor", "rotulo": "Acesso ao decisor", "valor": 0, "peso": 0.1,
     "contribuicao": 0.0, "justificativa": "Ainda sem contatos mapeados."},
]


@pytest.fixture
def admin_headers(client, admin):
    return _token(client, admin.email)


def _empresa_qualificada(db, score=62, faixa="morno"):
    empresa = Empresa(nome="Hospital Q", dominio="q.com.br", fonte="manual",
                      estado=EstadoProspect.mapeando_decisores, score=score)
    db.add(empresa)
    db.flush()
    db.add(Qualificacao(empresa_id=empresa.id, score=score, faixa=faixa, componentes_json=COMPONENTES,
                        pesos_json=PESOS, regra_versao="regra-v1"))
    db.commit()
    return empresa


def test_ficha_traz_a_qualificacao_com_os_componentes(client, db, vendedor_headers):
    empresa = _empresa_qualificada(db)
    q = client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers).json()["qualificacao"]
    assert (q["score"], q["faixa"], q["rotulo_faixa"], q["proximo_passo"]) == (62, "morno", "Morno",
                                                                              "abordagem padrão")
    assert [c["chave"] for c in q["componentes"]] == ["fit_icp", "acessibilidade_decisor"]
    assert q["regra_versao"] == "regra-v1"


def test_ficha_sem_qualificacao_vem_vazia(client, db, vendedor_headers):
    empresa = Empresa(nome="Nova", dominio="nova.com.br", fonte="manual", estado=EstadoProspect.novo)
    db.add(empresa)
    db.commit()
    ficha = client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers).json()
    assert ficha["qualificacao"] is None
    r = client.get(f"/empresas/{empresa.id}/qualificacao", headers=vendedor_headers)
    assert r.status_code == 404


def test_vale_a_qualificacao_mais_recente(client, db, vendedor_headers):
    from datetime import UTC, datetime, timedelta

    empresa = _empresa_qualificada(db, score=40, faixa="frio")
    db.add(Qualificacao(empresa_id=empresa.id, score=75, faixa="quente", componentes_json=COMPONENTES,
                        pesos_json=PESOS, regra_versao="regra-v1",
                        criado_em=datetime.now(UTC) + timedelta(minutes=1)))
    db.commit()
    q = client.get(f"/empresas/{empresa.id}/qualificacao", headers=vendedor_headers).json()
    assert (q["score"], q["rotulo_faixa"]) == (75, "Quente")


def test_config_do_score_usa_o_padrao_quando_falta_no_banco(client, vendedor_headers):
    r = client.get("/config/score", headers=vendedor_headers)
    assert r.status_code == 200
    assert r.json() == {"pesos": PESOS, "faixas": {"quente": 70, "morno": 45}}


def test_admin_altera_pesos_e_faixas_e_fica_registrado(client, db, admin, admin_headers):
    novo = {"pesos": {**PESOS, "fit_icp": 0.20, "intencao": 0.35}, "faixas": {"quente": 75, "morno": 50}}
    r = client.put("/config/score", json=novo, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json() == novo
    assert db.get(Config, "score_pesos").valor_json["intencao"] == 0.35
    evento = db.query(Evento).filter(Evento.tipo == "config_score_alterada").one()
    assert evento.empresa_id is None and evento.origem == "humano"
    assert evento.dados_json["antes"]["faixas"] == {"quente": 70, "morno": 45}
    assert evento.dados_json["depois"]["faixas"] == {"quente": 75, "morno": 50}


@pytest.mark.parametrize(
    "corpo, mensagem",
    [
        (
            {"pesos": {**PESOS, "fit_icp": 0.50}, "faixas": {"quente": 70, "morno": 45}},
            "somar 100% (hoje somam 120%)",
        ),
        ({"pesos": PESOS, "faixas": {"quente": 45, "morno": 70}}, "faixa Morno precisa ser menor"),
    ],
)
def test_configuracao_incoerente_e_recusada_com_mensagem(client, admin_headers, corpo, mensagem):
    r = client.put("/config/score", json=corpo, headers=admin_headers)
    assert r.status_code == 422
    assert mensagem in r.json()["detail"]


def test_vendedor_e_leitura_nao_alteram_o_score(client, vendedor_headers, leitura_headers):
    corpo = {"pesos": PESOS, "faixas": {"quente": 70, "morno": 45}}
    assert client.put("/config/score", json=corpo, headers=vendedor_headers).status_code == 403
    assert client.put("/config/score", json=corpo, headers=leitura_headers).status_code == 403


def test_sem_login_nada_e_exposto(client, db):
    empresa = _empresa_qualificada(db)
    assert client.get("/config/score").status_code == 401
    assert client.get(f"/empresas/{empresa.id}/qualificacao").status_code == 401
