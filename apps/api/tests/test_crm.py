"""Fase 2, Tarefa 4: CRM Kanban (quadro, mudança manual de estado registrada, funil)."""

import pytest

from app.crm import destinos_manuais, transicao_permitida
from app.models import Auditoria, Contato, Empresa, EstadoProspect, Evento, Qualificacao
from app.models import EstadoProspect as E

PESOS = {"fit_icp": 0.3}


def _empresa(
    db, nome, estado, score=None, faixa=None, nota=None, setor="saude", responsavel=None, dominio=None
):
    empresa = Empresa(
        nome=nome,
        dominio=dominio or f"{nome.lower().replace(' ', '-')}.com.br",
        fonte="manual",
        estado=estado,
        score=score,
        setor=setor,
        responsavel_id=responsavel,
    )
    db.add(empresa)
    db.flush()
    if faixa:
        db.add(
            Qualificacao(
                empresa_id=empresa.id,
                score=score or 0,
                faixa=faixa,
                componentes_json=[],
                pesos_json=PESOS,
                regra_versao="regra-v1",
            )
        )
    if nota is not None:
        db.add(Auditoria(empresa_id=empresa.id, nota=nota, achados_json={}, paginas_json=[], totais_json={}))
    db.commit()
    return empresa


def _coluna(quadro, estado):
    return next(c for c in quadro["colunas"] if c["estado"] == estado)


# --- Regras de transição ---------------------------------------------------------


@pytest.mark.parametrize(
    "origem, destino, ok",
    [
        (E.qualificando, E.arquivado, True),
        (E.pesquisando, E.arquivado, True),
        (E.arquivado, E.qualificando, True),
        (E.qualificando, E.mapeando_decisores, True),
        (E.preparando_abordagem, E.reuniao_agendada, True),
        (E.reuniao_agendada, E.proposta_enviada, True),
        (E.proposta_enviada, E.ganho, True),
        (E.negociacao, E.perdido, True),
        (E.qualificando, E.preparando_abordagem, False),  # quem leva é o Mapeador (contato verificado)
        (E.novo, E.pesquisando, False),  # passo do sistema
        (E.preparando_abordagem, E.em_sequencia, False),  # Fase 3
        (E.mapeando_decisores, E.reuniao_agendada, False),
        (E.ganho, E.arquivado, False),
        (E.reuniao_agendada, E.ganho, False),
    ],
)
def test_tabela_de_transicoes_manuais(origem, destino, ok):
    assert transicao_permitida(origem, destino) is ok


def test_destinos_seguem_a_ordem_do_quadro_e_marcam_o_motivo_obrigatorio():
    destinos = destinos_manuais(E.proposta_enviada)
    assert [(d.rotulo, d.motivo_obrigatorio) for d in destinos] == [
        ("Negociação", False),
        ("Ganho", False),
        ("Perdido", True),
        ("Arquivado", True),
    ]


# --- Quadro --------------------------------------------------------------------


def test_quadro_tem_todas_as_colunas_do_7_1_e_cartoes_completos(client, db, admin, vendedor_headers):
    frio = _empresa(
        db, "Hospital Frio", E.qualificando, score=30, faixa="frio", nota=80, responsavel=admin.id
    )
    _empresa(db, "Hospital Quente", E.preparando_abordagem, score=88, faixa="quente", nota=12)
    sem = _empresa(db, "Clinica Sem", E.mapeando_decisores, score=70, faixa="morno")
    db.add(
        Contato(empresa_id=sem.id, nome="X", area="TI", email=None, email_status="sem_email", fonte="apollo")
    )
    db.commit()
    q = client.get("/crm/quadro", headers=vendedor_headers).json()
    assert [c["rotulo"] for c in q["colunas"]][:6] == [
        "Novo",
        "Pesquisando",
        "Auditando",
        "Qualificando",
        "Mapeando decisores",
        "Preparando abordagem",
    ]
    assert len(q["colunas"]) == 16 and q["total"] == 3
    assert _coluna(q, "EM_SEQUENCIA")["fase_3"] is True

    cartao = _coluna(q, "QUALIFICANDO")["cartoes"][0]
    assert cartao["id"] == str(frio.id)
    assert (cartao["score"], cartao["rotulo_faixa"], cartao["nota_acessibilidade"]) == (30, "Frio", 80)
    assert cartao["proximo_passo"] == "Decidir: seguir ou arquivar"
    assert cartao["responsavel"] == "Admin"
    assert [d["estado"] for d in cartao["destinos"]] == ["MAPEANDO_DECISORES", "ARQUIVADO"]
    assert _coluna(q, "MAPEANDO_DECISORES")["cartoes"][0]["proximo_passo"] == (
        "Sem decisor com e-mail verificado: decidir"
    )


def test_cartao_com_problema_avisa_no_proximo_passo(client, db, vendedor_headers):
    e = _empresa(db, "Site Fora", E.pesquisando)
    db.add(Evento(empresa_id=e.id, tipo="site_indisponivel", origem="sistema", dados_json={"mensagem": "x"}))
    db.commit()
    cartao = _coluna(client.get("/crm/quadro", headers=vendedor_headers).json(), "PESQUISANDO")["cartoes"][0]
    assert cartao["problema"] == "site não pôde ser lido"
    assert cartao["proximo_passo"] == "Ver na ficha: site não pôde ser lido"


def test_filtros_do_quadro(client, db, vendedor_headers, admin):
    _empresa(db, "Hospital Alfa", E.qualificando, score=80, faixa="quente", setor="saude")
    _empresa(db, "Faculdade Beta", E.qualificando, score=40, faixa="frio", setor="educacao")
    vendedor = db.query(type(admin)).filter_by(email="vendedor@exemplo.com").one()
    _empresa(db, "Loja Gama", E.novo, setor="ecommerce", responsavel=vendedor.id)

    def nomes(**params):
        q = client.get("/crm/quadro", params=params, headers=vendedor_headers).json()
        return sorted(c["nome"] for col in q["colunas"] for c in col["cartoes"])

    assert nomes(busca="beta") == ["Faculdade Beta"]
    assert nomes(busca="alfa.com") == ["Hospital Alfa"]  # busca também no domínio
    assert nomes(setor="saude") == ["Hospital Alfa"]
    assert nomes(faixa="frio") == ["Faculdade Beta"]
    assert nomes(minhas="true") == ["Loja Gama"]


# --- Mudança manual de estado ------------------------------------------------


def test_mover_registra_evento_com_quem_de_onde_para_onde_e_por_que(client, db, vendedor_headers):
    e = _empresa(db, "Hospital M", E.qualificando, score=30, faixa="frio")
    r = client.post(
        f"/empresas/{e.id}/estado",
        json={"origem": "QUALIFICANDO", "destino": "ARQUIVADO", "motivo": "Fora do perfil"},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "ARQUIVADO" and r.json()["proximo_passo"] == "Arquivado; pode ser reaberto"
    db.expire_all()
    assert db.get(Empresa, e.id).estado == EstadoProspect.arquivado
    evento = db.query(Evento).filter(Evento.empresa_id == e.id).one()
    assert (evento.tipo, evento.origem) == ("estado_alterado_manual", "humano")
    assert (
        evento.dados_json["mensagem"]
        == "vendedor moveu de Qualificando para Arquivado. Motivo: Fora do perfil"
    )
    assert (evento.dados_json["origem_estado"], evento.dados_json["destino_estado"]) == (
        "QUALIFICANDO",
        "ARQUIVADO",
    )


def test_arquivar_exige_motivo(client, db, vendedor_headers):
    e = _empresa(db, "Hospital N", E.qualificando)
    r = client.post(
        f"/empresas/{e.id}/estado",
        json={"origem": "QUALIFICANDO", "destino": "ARQUIVADO", "motivo": "  "},
        headers=vendedor_headers,
    )
    assert r.status_code == 422 and r.json()["detail"] == "Explique o motivo para mover para Arquivado."


def test_destino_bloqueado_responde_com_mensagem(client, db, vendedor_headers):
    e = _empresa(db, "Hospital O", E.qualificando)
    r = client.post(
        f"/empresas/{e.id}/estado",
        json={"origem": "QUALIFICANDO", "destino": "EM_SEQUENCIA"},
        headers=vendedor_headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "Não é possível mover de Qualificando para Em sequência à mão."


def test_estado_mudou_no_meio_do_caminho_responde_409(client, db, vendedor_headers):
    e = _empresa(db, "Hospital P", E.mapeando_decisores)
    r = client.post(
        f"/empresas/{e.id}/estado",
        json={"origem": "QUALIFICANDO", "destino": "MAPEANDO_DECISORES"},
        headers=vendedor_headers,
    )
    assert r.status_code == 409 and "agora está em Mapeando decisores" in r.json()["detail"]
    assert db.query(Evento).count() == 0


def test_leitura_nao_move(client, db, leitura_headers):
    e = _empresa(db, "Hospital Q", E.qualificando)
    r = client.post(
        f"/empresas/{e.id}/estado",
        json={"origem": "QUALIFICANDO", "destino": "ARQUIVADO", "motivo": "x"},
        headers=leitura_headers,
    )
    assert r.status_code == 403


def test_ficha_traz_os_destinos_manuais(client, db, vendedor_headers):
    e = _empresa(db, "Hospital R", E.preparando_abordagem)
    destinos = client.get(f"/empresas/{e.id}/ficha", headers=vendedor_headers).json()["destinos"]
    assert [d["estado"] for d in destinos] == ["REUNIAO_AGENDADA", "ARQUIVADO"]


def test_funil(client, db, vendedor_headers):
    for nome, estado in [
        ("A", E.novo),
        ("B", E.qualificando),
        ("C", E.preparando_abordagem),
        ("D", E.reuniao_agendada),
        ("E", E.arquivado),
    ]:
        _empresa(db, nome, estado)
    assert client.get("/crm/funil", headers=vendedor_headers).json() == {
        "prospects": 4,
        "qualificados": 3,
        "com_decisores": 2,
        "reunioes": 1,
    }
