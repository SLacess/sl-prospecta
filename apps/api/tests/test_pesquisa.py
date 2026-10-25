"""Tarefa 2: confirmação do site pelo vendedor e resumo do dossiê na ficha."""

import uuid

from app.models import Dossie, Empresa, EstadoProspect, Evento
from app.timeline import registrar_evento

CANDIDATOS = [
    {
        "dominio": "unimed-a.com.br",
        "nome_oficial": "Unimed A",
        "evidencia_url": "https://unimed-a.com.br/",
        "confianca": "media",
    },
    {
        "dominio": "unimed-b.com.br",
        "nome_oficial": "Unimed B",
        "evidencia_url": "https://unimed-b.com.br/",
        "confianca": "media",
    },
]


def _empresa_aguardando_site(db, nome="Unimed"):
    empresa = Empresa(nome=nome, dominio=None, fonte="manual", estado=EstadoProspect.pesquisando)
    db.add(empresa)
    db.flush()
    registrar_evento(
        db,
        empresa.id,
        "confirmacao_dominio",
        "sistema",
        "Encontrei 2 site(s) possível(is). Confirme qual é o oficial para continuar.",
        candidatos=CANDIDATOS,
    )
    db.commit()
    return empresa


def test_ficha_mostra_os_candidatos_pendentes(client, db, vendedor_headers):
    empresa = _empresa_aguardando_site(db)
    r = client.get(f"/empresas/{empresa.id}", headers=vendedor_headers)
    assert r.status_code == 200
    confirmacao = r.json()["confirmacao_dominio"]
    assert [c["dominio"] for c in confirmacao["candidatos"]] == ["unimed-a.com.br", "unimed-b.com.br"]
    assert "Confirme" in confirmacao["mensagem"]
    assert r.json()["dossie"] is None


def test_vendedor_confirma_o_site_e_a_pesquisa_volta_para_a_fila(client, db, fila, vendedor_headers):
    empresa = _empresa_aguardando_site(db)
    r = client.post(
        f"/empresas/{empresa.id}/dominio",
        json={"dominio": "https://www.Unimed-B.com.br/"},
        headers=vendedor_headers,
    )
    assert r.status_code == 200
    assert r.json()["dominio"] == "unimed-b.com.br"
    assert fila.enviados == [empresa.id]

    detalhe = client.get(f"/empresas/{empresa.id}", headers=vendedor_headers).json()
    assert detalhe["confirmacao_dominio"] is None
    assert [e["tipo"] for e in detalhe["eventos"]][-2:] == ["dominio_confirmado", "enfileirado"]
    assert detalhe["eventos"][-2]["origem"] == "humano"


def test_site_de_outra_empresa_nao_e_aceito(client, db, fila, vendedor_headers):
    db.add(Empresa(nome="Unimed B Oficial", dominio="unimed-b.com.br", fonte="manual"))
    db.commit()
    empresa = _empresa_aguardando_site(db)
    r = client.post(
        f"/empresas/{empresa.id}/dominio", json={"dominio": "unimed-b.com.br"}, headers=vendedor_headers
    )
    assert r.status_code == 409
    assert "Unimed B Oficial" in r.json()["detail"]
    assert fila.enviados == []


def test_site_invalido_responde_422(client, db, fila, vendedor_headers):
    empresa = _empresa_aguardando_site(db)
    r = client.post(f"/empresas/{empresa.id}/dominio", json={"dominio": "10.0.0.1"}, headers=vendedor_headers)
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], str)


def test_empresa_que_ja_tem_site_nao_troca(client, db, fila, vendedor_headers):
    empresa = Empresa(nome="X", dominio="x.com.br", fonte="manual", estado=EstadoProspect.pesquisando)
    db.add(empresa)
    db.commit()
    r = client.post(f"/empresas/{empresa.id}/dominio", json={"dominio": "y.com.br"}, headers=vendedor_headers)
    assert r.status_code == 409


def test_leitura_nao_confirma_site(client, db, fila, leitura_headers):
    empresa = _empresa_aguardando_site(db)
    r = client.post(
        f"/empresas/{empresa.id}/dominio", json={"dominio": "unimed-a.com.br"}, headers=leitura_headers
    )
    assert r.status_code == 403


def test_confirmar_em_empresa_inexistente_404(client, fila, vendedor_headers):
    r = client.post(
        f"/empresas/{uuid.uuid4()}/dominio", json={"dominio": "a.com.br"}, headers=vendedor_headers
    )
    assert r.status_code == 404


def test_ficha_traz_o_resumo_do_dossie_mais_recente(client, db, vendedor_headers):
    empresa = Empresa(
        nome="Hospital", dominio="hospital.com.br", fonte="manual", estado=EstadoProspect.pesquisando
    )
    db.add(empresa)
    db.flush()
    db.add(Dossie(empresa_id=empresa.id, versao=1, resumo="antigo", dados_json={"setor": "outro"}))
    db.add(
        Dossie(empresa_id=empresa.id, versao=2, resumo="L1\nL2\n\nL3\nL4\nL5", dados_json={"setor": "saude"})
    )
    db.commit()

    dossie = client.get(f"/empresas/{empresa.id}", headers=vendedor_headers).json()["dossie"]
    assert dossie["versao"] == 2
    assert dossie["setor"] == "saude"
    assert dossie["resumo"] == ["L1", "L2", "L3", "L4", "L5"]


def test_empresa_em_pesquisa_sem_dossie_volta_para_a_fila(client, db, fila, vendedor_headers):
    """Ex.: a pesquisa falhou; reenviar a mesma empresa pelo painel tenta de novo."""
    empresa = Empresa(nome="h.com.br", dominio="h.com.br", fonte="manual", estado=EstadoProspect.pesquisando)
    db.add(empresa)
    db.commit()
    r = client.post("/prospeccao", json={"alvo": "h.com.br"}, headers=vendedor_headers)
    assert r.json()["duplicada"] is True
    assert r.json()["na_fila"] is True
    assert fila.enviados == [empresa.id]


def test_empresa_com_dossie_nao_volta_para_a_fila(client, db, fila, vendedor_headers):
    empresa = Empresa(nome="h.com.br", dominio="h.com.br", fonte="manual", estado=EstadoProspect.pesquisando)
    db.add(empresa)
    db.flush()
    db.add(Dossie(empresa_id=empresa.id, versao=1, resumo="x", dados_json={}))
    db.commit()
    r = client.post("/prospeccao", json={"alvo": "h.com.br"}, headers=vendedor_headers)
    assert r.json()["na_fila"] is False
    assert fila.enviados == []
    assert db.query(Evento).filter(Evento.tipo == "enfileirado").count() == 0
