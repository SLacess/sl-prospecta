import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.domain import EntradaInvalida, interpretar_entrada, normalizar_dominio
from app.models import Empresa, EstadoProspect


def _tipos(client, headers, empresa_id):
    r = client.get(f"/empresas/{empresa_id}", headers=headers)
    assert r.status_code == 200
    return [e["tipo"] for e in r.json()["eventos"]]


# --- Normalização da entrada -------------------------------------------------

@pytest.mark.parametrize("entrada", [
    "hospitalexemplo.com.br",
    "HOSPITALEXEMPLO.COM.BR",
    "www.hospitalexemplo.com.br",
    "https://www.hospitalexemplo.com.br/contato?x=1#topo",
    "http://hospitalexemplo.com.br:8080",
    "  hospitalexemplo.com.br/  ",
    "hospitalexemplo.com.br.",
])
def test_formas_do_mesmo_site_viram_o_mesmo_dominio(entrada):
    alvo = interpretar_entrada(entrada)
    assert alvo.tipo == "url"
    assert alvo.dominio == "hospitalexemplo.com.br"


def test_dominio_com_acento_vira_idna():
    assert normalizar_dominio("açaí.com.br").startswith("xn--")


@pytest.mark.parametrize("entrada", ["Hospital Exemplo", "Ambev S.A.", "Grupo Educacional São Lucas"])
def test_nome_sem_dominio(entrada):
    alvo = interpretar_entrada(entrada)
    assert alvo.tipo == "nome"
    assert alvo.dominio is None


@pytest.mark.parametrize("entrada", ["", "   ", "@@@", "a", "192.168.0.10", "http://", "exemplo.c0m"])
def test_entradas_invalidas(entrada):
    with pytest.raises(EntradaInvalida):
        interpretar_entrada(entrada)


# --- POST /prospeccao --------------------------------------------------------

def test_url_cria_empresa_em_novo_registra_evento_e_enfileira(client, fila, vendedor_headers):
    r = client.post("/prospeccao", json={"alvo": "https://www.Hospital-Exemplo.com.br/contato"},
                    headers=vendedor_headers)
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["duplicada"] is False
    assert corpo["na_fila"] is True
    assert corpo["fila_pausada"] is False
    assert corpo["empresa"]["dominio"] == "hospital-exemplo.com.br"
    assert corpo["empresa"]["estado"] == EstadoProspect.novo.value
    assert corpo["empresa"]["fonte"] == "manual"

    empresa_id = uuid.UUID(corpo["empresa"]["id"])
    assert fila.enviados == [empresa_id]
    assert _tipos(client, vendedor_headers, empresa_id) == ["entrada_recebida", "enfileirado"]


def test_deduplica_por_dominio(client, db, fila, vendedor_headers):
    r1 = client.post("/prospeccao", json={"alvo": "hospitalexemplo.com.br"}, headers=vendedor_headers)
    r2 = client.post("/prospeccao", json={"alvo": "HTTPS://WWW.HOSPITALEXEMPLO.COM.BR:443/sobre"},
                     headers=vendedor_headers)

    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    assert r2.json()["empresa"]["id"] == r1.json()["empresa"]["id"]
    assert "já está cadastrada" in r2.json()["mensagem"]
    assert db.scalar(select(func.count()).select_from(Empresa)) == 1
    # A fila não recebe um segundo job da mesma empresa
    assert len(fila.enviados) == 1
    assert _tipos(client, vendedor_headers, r1.json()["empresa"]["id"]) == [
        "entrada_recebida", "enfileirado", "entrada_duplicada",
    ]


def test_nome_cria_empresa_sem_dominio_e_deduplica_pelo_nome(client, db, fila, vendedor_headers):
    r1 = client.post("/prospeccao", json={"alvo": "Hospital Exemplo"}, headers=vendedor_headers)
    r2 = client.post("/prospeccao", json={"alvo": "  hospital   EXEMPLO "}, headers=vendedor_headers)

    assert r1.status_code == 201
    assert r1.json()["empresa"]["dominio"] is None
    assert r1.json()["empresa"]["nome"] == "Hospital Exemplo"
    assert r2.status_code == 200
    assert r2.json()["empresa"]["id"] == r1.json()["empresa"]["id"]
    assert db.scalar(select(func.count()).select_from(Empresa)) == 1


def test_empresa_fora_de_novo_nao_volta_para_a_fila(client, db, fila, vendedor_headers):
    r1 = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    empresa = db.get(Empresa, uuid.UUID(r1.json()["empresa"]["id"]))
    empresa.estado = EstadoProspect.qualificando
    db.commit()
    fila.enviados.clear()

    r2 = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    assert r2.json()["duplicada"] is True
    assert r2.json()["na_fila"] is False
    assert fila.enviados == []


@pytest.mark.parametrize("entrada", ["", "   ", "@@@", "192.168.0.10"])
def test_entrada_invalida_responde_422_com_mensagem(client, fila, vendedor_headers, entrada):
    r = client.post("/prospeccao", json={"alvo": entrada}, headers=vendedor_headers)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)
    assert fila.enviados == []


def test_prospeccao_exige_login(client, fila):
    assert client.post("/prospeccao", json={"alvo": "exemplo.com.br"}).status_code == 401


def test_perfil_leitura_nao_prospecta(client, fila, leitura_headers):
    r = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=leitura_headers)
    assert r.status_code == 403


def test_fila_indisponivel_responde_503_e_registra_falha(client, db, fila, vendedor_headers):
    fila.indisponivel = True
    r = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    assert r.status_code == 503
    assert "indisponível" in r.json()["detail"]

    empresa = db.scalar(select(Empresa).where(Empresa.dominio == "exemplo.com.br"))
    assert empresa is not None
    assert _tipos(client, vendedor_headers, empresa.id) == ["entrada_recebida", "falha_enfileirar"]

    # Ao tentar de novo com a fila de volta, a mesma empresa entra na fila
    fila.indisponivel = False
    r2 = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    assert r2.status_code == 200
    assert r2.json()["na_fila"] is True
    assert fila.enviados == [empresa.id]


def test_disjuntor_atingido_avisa_na_resposta(client, fila, vendedor_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "daily_ai_budget_brl", Decimal("0"))
    r = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    assert r.status_code == 201
    assert r.json()["fila_pausada"] is True
    assert r.json()["na_fila"] is True  # o job fica na fila; o worker adia até o orçamento reabrir
    assert "teto diário" in r.json()["mensagem"]


# --- GET /empresas/{id} ------------------------------------------------------

def test_empresa_inexistente_404(client, vendedor_headers):
    assert client.get(f"/empresas/{uuid.uuid4()}", headers=vendedor_headers).status_code == 404


def test_leitura_ve_a_linha_do_tempo(client, fila, vendedor_headers, leitura_headers):
    r = client.post("/prospeccao", json={"alvo": "exemplo.com.br"}, headers=vendedor_headers)
    detalhe = client.get(f"/empresas/{r.json()['empresa']['id']}", headers=leitura_headers)
    assert detalhe.status_code == 200
    primeiro = detalhe.json()["eventos"][0]
    assert primeiro["mensagem"] == "Empresa cadastrada a partir do site exemplo.com.br."
    assert primeiro["origem"] == "humano"
