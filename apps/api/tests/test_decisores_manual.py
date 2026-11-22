"""Decisor cadastrado à mão (CONSTITUICAO §7.3, Etapa 4): só quando o Mapeador já tentou e não achou
ninguém — nunca um atalho para pular a busca automática."""

import uuid

from app.models import Contato, Empresa, EstadoProspect, Evento


def _empresa_mapeando(db, *, com_tentativa=True, nome="Sinal Link", sufixo="") -> Empresa:
    empresa = Empresa(
        nome=nome, dominio=f"sinallink{sufixo}.com.br", fonte="manual",
        estado=EstadoProspect.mapeando_decisores,
    )
    db.add(empresa)
    db.flush()
    if com_tentativa:
        db.add(Evento(empresa_id=empresa.id, tipo="sem_decisores", origem="sistema", dados_json={}))
    db.commit()
    return empresa


def _payload(**sobrescreve):
    base = {"nome": "Marcos", "sobrenome": "Alencar", "email": "marcos@sinallink.com.br",
            "cargo": "Fundador", "area": "TI"}
    base.update(sobrescreve)
    return base


def test_leitura_nao_pode_adicionar(client, db, vendedor_headers, leitura_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores", json={"decisores": [_payload()]}, headers=leitura_headers
    )
    assert r.status_code == 403


def test_vendedor_pode_adicionar(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores", json={"decisores": [_payload()]}, headers=vendedor_headers
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["empresa"]["estado"] == "PREPARANDO_ABORDAGEM"
    assert corpo["permite_decisor_manual"] is False
    [decisor] = corpo["decisores"]
    assert decisor["nome"] == "Marcos Alencar"
    assert decisor["email"] == "marcos@sinallink.com.br"
    assert decisor["email_status"] == "valido"
    assert decisor["fonte"] == "manual"

    with_contato = db.query(Contato).filter(Contato.empresa_id == empresa.id).one()
    assert with_contato.area == "TI"
    evento = db.query(Evento).filter(Evento.tipo == "decisor_adicionado_manual").one()
    assert "Marcos Alencar" in evento.dados_json["mensagem"]
    assert "Preparando abordagem" in evento.dados_json["mensagem"]


def test_sem_email_nao_avanca_estado(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores",
        json={"decisores": [_payload(email=None)]},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["empresa"]["estado"] == "MAPEANDO_DECISORES"
    assert corpo["permite_decisor_manual"] is True  # ainda sem decisor válido — pode tentar de novo
    assert corpo["decisores"][0]["email_status"] == "sem_email"


def test_varios_decisores_de_uma_vez(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores",
        json={"decisores": [
            _payload(nome="Marcos", email="marcos@sinallink.com.br"),
            _payload(nome="Ana", sobrenome="Souza", email=None, area="RH"),
        ]},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["decisores"]) == 2
    assert r.json()["empresa"]["estado"] == "PREPARANDO_ABORDAGEM"


def test_estado_errado_e_409(client, db, vendedor_headers):
    empresa = Empresa(nome="X", dominio="x.com.br", fonte="manual", estado=EstadoProspect.qualificando)
    db.add(empresa)
    db.commit()
    r = client.post(
        f"/empresas/{empresa.id}/decisores", json={"decisores": [_payload()]}, headers=vendedor_headers
    )
    assert r.status_code == 409


def test_sem_tentativa_automatica_e_409(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db, com_tentativa=False)
    r = client.post(
        f"/empresas/{empresa.id}/decisores", json={"decisores": [_payload()]}, headers=vendedor_headers
    )
    assert r.status_code == 409


def test_ja_tem_decisor_valido_e_409(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    db.add(Contato(
        empresa_id=empresa.id, nome="Alguém", area="TI", email="alguem@sinallink.com.br",
        email_status="valido", opt_out=False, fonte="apollo",
    ))
    db.commit()
    r = client.post(
        f"/empresas/{empresa.id}/decisores", json={"decisores": [_payload()]}, headers=vendedor_headers
    )
    assert r.status_code == 409


def test_email_duplicado_na_empresa_e_422(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores",
        json={"decisores": [
            _payload(nome="Marcos", email="duplicado@sinallink.com.br"),
            _payload(nome="Outro", email="duplicado@sinallink.com.br"),
        ]},
        headers=vendedor_headers,
    )
    assert r.status_code == 422


def test_area_invalida_e_422(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db)
    r = client.post(
        f"/empresas/{empresa.id}/decisores",
        json={"decisores": [_payload(area="Financeiro")]},
        headers=vendedor_headers,
    )
    assert r.status_code == 422


def test_empresa_inexistente_e_404(client, vendedor_headers):
    r = client.post(
        f"/empresas/{uuid.uuid4()}/decisores", json={"decisores": [_payload()]}, headers=vendedor_headers
    )
    assert r.status_code == 404


def test_ficha_sem_tentativa_nao_permite_decisor_manual(client, db, vendedor_headers):
    empresa = _empresa_mapeando(db, com_tentativa=False)
    r = client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    assert r.json()["permite_decisor_manual"] is False
