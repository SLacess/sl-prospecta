"""Guardião (Fase 3, Tarefa 4 — retomada; ADR 0016): Claude simulado, sem nenhuma chamada externa."""

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from slp_workers.agents.guardiao import AvaliacaoGuardiao
from slp_workers.db import contatos, eventos, sequencias, supressao, toques
from slp_workers.llm import Consumo
from slp_workers.orchestrator.guardiao import DependenciasGuardiao, Guardiao
from slp_workers.settings import WorkerConfig
from tests.conftest import inserir_empresa


class IAGuardiaoFalsa:
    def __init__(self, avaliacao: AvaliacaoGuardiao | None = None):
        self.avaliacao = avaliacao or AvaliacaoGuardiao(
            aprovado=True, motivo="Identificação, opt-out e tom conferem.", raciocinio_resumido="Ok."
        )
        self.chamadas = 0

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        assert formato is AvaliacaoGuardiao
        self.chamadas += 1
        return self.avaliacao, Consumo(modelo=modelo, custo_brl=Decimal("0.01"))


@pytest.fixture
def config():
    return WorkerConfig()


def _inserir_contato(engine, empresa_id, *, email="ana@exemplo.com.br") -> uuid.UUID:
    cid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            contatos.insert().values(
                id=cid, empresa_id=empresa_id, nome="Ana Souza", cargo="Gerente de TI", area="TI",
                email=email, email_status="valido", opt_out=False, fonte="apollo",
                criado_em=datetime.now(UTC),
            )
        )
    return cid


def _inserir_toque_aprovado(
    engine, empresa_id, contato_id, *, dia=0, corpo="Olá, Ana. Um achado real. Para sair, responda.",
    decisao_humana="aprovado", enviado_em=None,
) -> uuid.UUID:
    seq_id = uuid.uuid4()
    toque_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            sequencias.insert().values(
                id=seq_id, empresa_id=empresa_id, contato_id=contato_id, persona="ti",
                angulo="conformidade_legal", achado_titulo="Achado", achado_pagina_url="https://x",
                gancho_justificativa="g", criado_em=datetime.now(UTC),
            )
        )
        conn.execute(
            toques.insert().values(
                id=toque_id, sequencia_id=seq_id, dia=dia, canal="email", status="rascunho",
                conteudo_sugerido="x", assunto="assunto original", corpo="corpo original",
                assunto_final="Assunto final", corpo_final=corpo, decisao_humana=decisao_humana,
                enviado_em=enviado_em, criado_em=datetime.now(UTC),
            )
        )
    return toque_id


def test_nada_a_fazer_se_ainda_nao_aprovado(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id, decisao_humana=None)
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado is None
    assert ia.chamadas == 0


def test_nada_a_fazer_se_ja_enviado(engine, config):
    empresa_id = inserir_empresa(engine, estado="EM_SEQUENCIA")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id, enviado_em=datetime.now(UTC))
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado is None
    assert ia.chamadas == 0


def test_dominio_suprimido_bloqueia_sem_chamar_ia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM", dominio="suprimido.com.br")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id)
    with engine.begin() as conn:
        conn.execute(supressao.insert().values(id=uuid.uuid4(), dominio="suprimido.com.br", motivo="pediu"))
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "bloqueado"
    assert ia.chamadas == 0
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.guardiao_resultado == "bloqueado"
        assert "suprimido.com.br" in t.guardiao_motivo
        tipos = {e.tipo for e in conn.execute(select(eventos))}
        assert tipos == {"guardiao_bloqueou"}


def test_email_suprimido_bloqueia_sem_chamar_ia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id, email="suprimido@exemplo.com.br")
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id)
    with engine.begin() as conn:
        conn.execute(
            supressao.insert().values(id=uuid.uuid4(), email="suprimido@exemplo.com.br", motivo="pediu")
        )
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "bloqueado"
    assert ia.chamadas == 0


def test_mais_de_um_link_no_dia_zero_bloqueia_sem_chamar_ia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(
        engine, empresa_id, contato_id, dia=0,
        corpo="Veja https://a.com.br e também https://b.com.br",
    )
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "bloqueado"
    assert ia.chamadas == 0
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert "15.2" in t.guardiao_motivo


def test_mais_de_um_link_fora_do_dia_zero_nao_bloqueia_por_regra(engine, config):
    empresa_id = inserir_empresa(engine, estado="EM_SEQUENCIA")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(
        engine, empresa_id, contato_id, dia=3,
        corpo="Veja https://a.com.br e também https://b.com.br",
    )
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "aprovado"
    assert ia.chamadas == 1


def test_ia_reprova_grava_bloqueado_e_acao(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id)
    ia = IAGuardiaoFalsa(
        AvaliacaoGuardiao(aprovado=False, motivo="Promete acessibilidade total.", raciocinio_resumido="x")
    )

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "bloqueado"
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.guardiao_resultado == "bloqueado"
        assert t.guardiao_motivo == "Promete acessibilidade total."
        assert t.guardiao_avaliado_em is not None


def test_ia_aprova_grava_aprovado_e_registra_acao_e_evento(engine, config):
    from slp_workers.db import acoes_agentes

    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque_aprovado(engine, empresa_id, contato_id)
    ia = IAGuardiaoFalsa()

    resultado = asyncio.run(Guardiao(DependenciasGuardiao(engine, ia, config), toque_id).executar())

    assert resultado == "aprovado"
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.guardiao_resultado == "aprovado"
        acoes = conn.execute(select(acoes_agentes).where(acoes_agentes.c.contato_id == contato_id)).all()
        assert [a.agente for a in acoes] == ["guardiao"]
        tipos = {e.tipo for e in conn.execute(select(eventos))}
        assert tipos == {"guardiao_aprovou"}
