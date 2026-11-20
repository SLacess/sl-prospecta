"""Fase 3, Tarefa 3: Caixa de Aprovação (CONSTITUICAO §12.1, item 4; ADR 0014, ponto 4)."""

from datetime import UTC, datetime
from difflib import SequenceMatcher

from app.models import Contato, Empresa, Evento, Sequencia, Toque
from app.models import EstadoProspect as E

ASSUNTO_ORIGINAL = "formulário de contato da Hospital M"
CORPO_ORIGINAL = (
    "Olá, Ana. No site da Hospital M encontramos um bloqueio de teclado no formulário de contato."
)


def _sequencia_com_toque(
    db,
    empresa_estado=E.preparando_abordagem,
    nota=8,
    aprovado_critico=True,
    status="rascunho",
    dia=0,
    assunto=ASSUNTO_ORIGINAL,
    corpo=CORPO_ORIGINAL,
    sufixo="",
):
    nome = f"Hospital M{sufixo}"
    empresa = Empresa(
        nome=nome, dominio=f"hospital-m{sufixo}.com.br", fonte="manual", estado=empresa_estado
    )
    db.add(empresa)
    db.flush()
    contato = Contato(
        empresa_id=empresa.id, nome="Ana Souza", area="TI", email=f"ana{sufixo}@hospital-m.com.br",
        email_status="valido", fonte="apollo",
    )
    db.add(contato)
    db.flush()
    seq = Sequencia(
        empresa_id=empresa.id, contato_id=contato.id, persona="ti", angulo="experiencia_cliente",
        achado_titulo="Bloqueio de teclado no formulário de contato",
        achado_pagina_url="https://hospital-m.com.br/contato",
        gancho_justificativa="Quem navega só pelo teclado não consegue enviar o formulário.",
    )
    db.add(seq)
    db.flush()
    toque = Toque(
        sequencia_id=seq.id, dia=dia, canal="email", status=status,
        conteudo_sugerido="achado principal + convite para ver o relatório",
        assunto=assunto, corpo=corpo, fatos_usados=["bloqueio de teclado"],
        criterios_json={"veracidade": nota}, nota=nota, aprovado=aprovado_critico,
        motivo_critico=None if aprovado_critico else "texto genérico", tentativas=1,
    )
    db.add(toque)
    db.commit()
    return empresa, contato, seq, toque


def test_listar_so_traz_dia0_rascunho_pendente(client, db, vendedor_headers):
    _, _, _, pendente = _sequencia_com_toque(db)
    # Um toque planejado (dia > 0, sem texto) não deve aparecer na fila
    _, _, seq2, _ = _sequencia_com_toque(db, sufixo="2")
    db.add(Toque(sequencia_id=seq2.id, dia=3, canal="email", status="planejada",
                 conteudo_sugerido="segundo achado"))
    db.commit()

    r = client.get("/caixa-aprovacao", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    ids = [item["toque_id"] for item in r.json()]
    assert str(pendente.id) in ids
    assert len(r.json()) == 2  # os dois toques "rascunho" criados por _sequencia_com_toque


def test_aprovar_sem_editar_zera_percentual(client, db, vendedor_headers):
    _, contato, _, toque = _sequencia_com_toque(db)
    r = client.post(
        f"/toques/{toque.id}/aprovar",
        json={"assunto": ASSUNTO_ORIGINAL, "corpo": CORPO_ORIGINAL},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["decisao_humana"] == "aprovado"
    assert float(corpo["percentual_editado"]) == 0.0
    assert corpo["assunto_final"] == ASSUNTO_ORIGINAL
    assert corpo["decidido_por_nome"] == "vendedor"


def test_aprovar_com_edicao_calcula_percentual(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    assunto_final = "formulário de contato"
    corpo_final = "Olá, Ana. Encontramos um problema de acessibilidade no formulário de contato do site."
    r = client.post(
        f"/toques/{toque.id}/aprovar",
        json={"assunto": assunto_final, "corpo": corpo_final},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    original = f"{ASSUNTO_ORIGINAL}\n\n{CORPO_ORIGINAL}"
    final = f"{assunto_final}\n\n{corpo_final}"
    esperado = round((1 - SequenceMatcher(None, original, final).ratio()) * 100, 2)
    assert abs(float(r.json()["percentual_editado"]) - esperado) < 0.01


def test_aprovar_com_texto_vazio_e_422(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    r = client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": "  ", "corpo": "  "}, headers=vendedor_headers
    )
    assert r.status_code == 422


def test_reaprovar_zera_avaliacao_anterior_do_guardiao(client, db, vendedor_headers):
    """ADR 0016: o texto pode ter mudado nesta aprovação — uma avaliação antiga do Guardião não vale mais."""
    _, _, _, toque = _sequencia_com_toque(db)
    toque.guardiao_resultado = "aprovado"
    toque.guardiao_motivo = "Tudo confere."
    toque.guardiao_avaliado_em = datetime.now(UTC)
    db.commit()

    r = client.post(
        f"/toques/{toque.id}/aprovar",
        json={"assunto": "outro assunto", "corpo": "outro corpo bem diferente do original"},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["guardiao_resultado"] is None
    assert corpo["guardiao_motivo"] is None
    assert corpo["guardiao_avaliado_em"] is None


def test_rejeitar_sem_motivo_e_422(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    r = client.post(f"/toques/{toque.id}/rejeitar", json={"motivo": "  "}, headers=vendedor_headers)
    assert r.status_code == 422


def test_rejeitar_registra_motivo_e_evento(client, db, vendedor_headers):
    empresa, contato, _, toque = _sequencia_com_toque(db)
    r = client.post(
        f"/toques/{toque.id}/rejeitar",
        json={"motivo": "Soa como modelo de vendas."},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["decisao_humana"] == "rejeitado"
    evento = db.query(Evento).filter(Evento.empresa_id == empresa.id).one()
    assert evento.tipo == "toque_rejeitado"
    assert "Soa como modelo de vendas." in evento.dados_json["mensagem"]
    db.expire_all()
    assert db.get(Empresa, empresa.id).estado == E.preparando_abordagem


def test_rejeitar_depois_aprovar_desfaz_a_rejeicao(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    client.post(f"/toques/{toque.id}/rejeitar", json={"motivo": "não serve"}, headers=vendedor_headers)
    r = client.post(
        f"/toques/{toque.id}/aprovar",
        json={"assunto": ASSUNTO_ORIGINAL, "corpo": CORPO_ORIGINAL},
        headers=vendedor_headers,
    )
    assert r.status_code == 200
    assert r.json()["decisao_humana"] == "aprovado"
    assert r.json()["motivo_rejeicao"] is None


def test_marcar_enviado_antes_de_aprovar_e_422(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    r = client.post(f"/toques/{toque.id}/enviado", headers=vendedor_headers)
    assert r.status_code == 422


def test_marcar_enviado_move_para_em_sequencia_e_e_idempotente_por_empresa(client, db, vendedor_headers):
    empresa, contato1, _, toque1 = _sequencia_com_toque(db)
    # Segundo contato/sequência da mesma empresa
    contato2 = Contato(
        empresa_id=empresa.id, nome="Beto Lima", area="ESG", email="beto@hospital-m.com.br",
        email_status="valido", fonte="apollo",
    )
    db.add(contato2)
    db.flush()
    seq2 = Sequencia(
        empresa_id=empresa.id, contato_id=contato2.id, persona="esg", angulo="esg_reputacao",
        achado_titulo="x", achado_pagina_url="https://hospital-m.com.br/x", gancho_justificativa="y",
    )
    db.add(seq2)
    db.flush()
    toque2 = Toque(
        sequencia_id=seq2.id, dia=0, canal="email", status="rascunho",
        conteudo_sugerido="x", assunto="assunto 2", corpo="corpo 2", nota=9, aprovado=True, tentativas=1,
    )
    db.add(toque2)
    db.commit()

    for t in (toque1, toque2):
        client.post(
            f"/toques/{t.id}/aprovar", json={"assunto": t.assunto, "corpo": t.corpo}, headers=vendedor_headers
        )

    r1 = client.post(f"/toques/{toque1.id}/enviado", headers=vendedor_headers)
    assert r1.status_code == 200, r1.text
    db.expire_all()
    assert db.get(Empresa, empresa.id).estado == E.em_sequencia
    assert db.query(Evento).filter(Evento.tipo == "entrou_em_sequencia").count() == 1

    r2 = client.post(f"/toques/{toque2.id}/enviado", headers=vendedor_headers)
    assert r2.status_code == 200, r2.text
    assert db.query(Evento).filter(Evento.tipo == "entrou_em_sequencia").count() == 1


def test_marcar_enviado_duas_vezes_e_409(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": toque.assunto, "corpo": toque.corpo},
        headers=vendedor_headers,
    )
    client.post(f"/toques/{toque.id}/enviado", headers=vendedor_headers)
    r = client.post(f"/toques/{toque.id}/enviado", headers=vendedor_headers)
    assert r.status_code == 409


def test_aprovar_depois_de_enviado_e_409(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": toque.assunto, "corpo": toque.corpo},
        headers=vendedor_headers,
    )
    client.post(f"/toques/{toque.id}/enviado", headers=vendedor_headers)
    r = client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": "outro", "corpo": "outro"}, headers=vendedor_headers
    )
    assert r.status_code == 409


def test_leitura_nao_decide(client, db, leitura_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    r = client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": "x", "corpo": "y"}, headers=leitura_headers
    )
    assert r.status_code == 403


def test_placar_conta_aprovados_dentro_da_meta(client, db, vendedor_headers):
    _, _, _, toque = _sequencia_com_toque(db)
    client.post(
        f"/toques/{toque.id}/aprovar", json={"assunto": ASSUNTO_ORIGINAL, "corpo": CORPO_ORIGINAL},
        headers=vendedor_headers,
    )
    r = client.get("/caixa-aprovacao/placar", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    placar = r.json()
    assert placar["meta"] == 50
    assert placar["aprovados"] == 1
    assert placar["aprovados_dentro_da_meta"] == 1
    assert placar["atingido"] is False
