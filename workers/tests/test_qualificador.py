"""Qualificador (Fase 2, Tarefa 1): regra do score do §7.3, faixas, config e gravação pelo orquestrador."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from slp_workers.agents.qualificador import (
    PESOS_PADRAO,
    ConfigInvalida,
    EntradaQualificacao,
    Qualificacao,
    faixa_do_score,
    qualificar,
)
from slp_workers.db import acoes_agentes, auditorias, config, dossies, empresas, eventos, qualificacoes
from slp_workers.orchestrator.pipeline import processar_empresa
from slp_workers.orchestrator.qualificacao import qualificar_e_gravar
from tests.conftest import inserir_empresa, montar_ctx

FAIXAS = {"quente": 70, "morno": 45}
ESQUEMA = Path(__file__).resolve().parents[2] / "packages" / "schemas" / "qualificacao.schema.json"


def _entrada(**alteracoes) -> EntradaQualificacao:
    base = dict(
        setor="saude", uf="SP", dominio="h.com.br", porte=None, porte_indicios=None,
        sinais=[], mencoes_inclusao=[], nota_auditoria=40, contatos_validos=0,
    )
    return EntradaQualificacao(**{**base, **alteracoes})


def _valor(q, chave):
    return next(c for c in q.componentes if c.chave == chave)


# --- Regra -------------------------------------------------------------------


def test_score_e_a_soma_ponderada_dos_cinco_componentes():
    q = qualificar(_entrada(sinais=[{"tipo": "relatorio_esg"}], mencoes_inclusao=[{}, {}, {}]))
    # Fit 60+20+10 = 90; Intenção 20 + menções (teto 20) = 40; Gravidade 60; Pressão saúde 75; Decisor 0
    assert [c.valor for c in q.componentes] == [90, 40, 60, 75, 0]
    assert q.score == round(90 * 0.30 + 40 * 0.25 + 60 * 0.20 + 75 * 0.15 + 0)  # 60
    assert q.faixa == "morno"
    assert q.regra_versao == "regra-v1"
    assert "Score 60 (morno)" in q.raciocinio_resumido


@pytest.mark.parametrize("score, faixa", [(44, "frio"), (45, "morno"), (69, "morno"), (70, "quente")])
def test_limites_das_faixas(score, faixa):
    assert faixa_do_score(score, FAIXAS) == faixa


def test_setor_fora_do_icp_e_pais_desconhecido_nao_pontuam():
    q = qualificar(_entrada(setor="outro", uf=None, dominio="exemplo.com"))
    fit = _valor(q, "fit_icp")
    assert fit.valor == 10  # só o porte neutro
    assert "fora da lista do ICP" in fit.justificativa
    assert "sem indício de atuação no Brasil" in fit.justificativa
    assert _valor(q, "pressao_regulatoria").valor == 40


def test_dominio_br_conta_como_brasil_quando_falta_a_uf():
    assert "domínio .br" in _valor(qualificar(_entrada(uf=None)), "fit_icp").justificativa


@pytest.mark.parametrize("porte, pontos", [("201-500", 20), ("1.000+", 20), ("11-50", 0), (None, 10)])
def test_porte_conta_pelo_minimo_do_icp(porte, pontos):
    fit = _valor(qualificar(_entrada(porte=porte)), "fit_icp")
    assert fit.valor == 60 + 20 + pontos


def test_porte_desconhecido_mostra_o_que_o_site_diz():
    fit = _valor(qualificar(_entrada(porte_indicios="12 unidades em SP")), "fit_icp")
    assert '"12 unidades em SP"' in fit.justificativa
    assert "SP" in fit.justificativa.split(";")[1]  # a UF não perde a caixa alta


def test_intencao_tem_teto_de_100_e_avisa_dos_sinais_nao_coletados():
    sinais = [{"tipo": t} for t in ("vaga_pcd_ou_inclusao", "relatorio_esg", "pagina_acessibilidade",
                                    "app_ou_portal", "app_ou_portal", "outro")]
    intencao = _valor(qualificar(_entrada(sinais=sinais, mencoes_inclusao=[{}] * 5)), "intencao")
    assert intencao.valor == 100
    assert "2× app ou portal do cliente" in intencao.justificativa
    assert "ainda não são coletados" in intencao.justificativa


def test_gravidade_e_o_inverso_da_nota():
    assert _valor(qualificar(_entrada(nota_auditoria=91)), "gravidade_barreiras").valor == 9
    assert _valor(qualificar(_entrada(nota_auditoria=0)), "gravidade_barreiras").valor == 100


def test_acesso_ao_decisor_fica_em_zero_sem_contatos():
    q = qualificar(_entrada())
    assert _valor(q, "acessibilidade_decisor").valor == 0
    assert _valor(qualificar(_entrada(contatos_validos=2)), "acessibilidade_decisor").valor == 100


def test_pesos_e_tabelas_vem_da_config():
    pesos = {**PESOS_PADRAO, "fit_icp": 0.20, "intencao": 0.35}
    q = qualificar(_entrada(), pesos=pesos, pressao_setor={"saude": 100})
    assert _valor(q, "fit_icp").peso == 0.20
    assert _valor(q, "pressao_regulatoria").valor == 100


@pytest.mark.parametrize(
    "pesos",
    [
        {**PESOS_PADRAO, "fit_icp": 0.50},  # soma 1,20
        {k: v for k, v in PESOS_PADRAO.items() if k != "intencao"},  # componente faltando
        {**PESOS_PADRAO, "fit_icp": -0.10, "intencao": 0.65},  # negativo
    ],
)
def test_pesos_invalidos_sao_recusados(pesos):
    with pytest.raises(ConfigInvalida):
        qualificar(_entrada(), pesos=pesos)


def test_faixas_invalidas_sao_recusadas():
    with pytest.raises(ConfigInvalida):
        qualificar(_entrada(), faixas={"quente": 40, "morno": 45})


def test_esquema_publicado_esta_atualizado():
    assert json.loads(ESQUEMA.read_text(encoding="utf-8")) == Qualificacao.model_json_schema()


# --- Orquestrador ------------------------------------------------------------


def _analisada(engine, *, setor="educacao", nota=10, estado="QUALIFICANDO", sinais=None):
    eid = inserir_empresa(engine, dominio=f"{uuid.uuid4().hex[:8]}.com.br", estado=estado)
    with engine.begin() as conn:
        conn.execute(empresas.update().where(empresas.c.id == eid).values(setor=setor, uf="SP"))
        conn.execute(
            auditorias.insert().values(
                id=uuid.uuid4(), empresa_id=eid, nota=nota, totais_json={}, achados_json={},
                paginas_json=[], artefatos_urls=[], criado_em=datetime.now(UTC),
            )
        )
        conn.execute(
            dossies.insert().values(
                id=uuid.uuid4(), empresa_id=eid, versao=1, resumo="", criado_em=datetime.now(UTC),
                dados_json={"porte_indicios": None},
                sinais_json={"sinais": sinais or [], "mencoes_inclusao": []},
            )
        )
    return eid


def _estado(engine, eid):
    with engine.connect() as conn:
        return conn.execute(select(empresas.c.estado, empresas.c.score).where(empresas.c.id == eid)).one()


def test_quente_ou_morno_segue_para_mapeando_decisores(engine):
    sinais = [{"tipo": "relatorio_esg"}, {"tipo": "vaga_pcd_ou_inclusao"}, {"tipo": "app_ou_portal"}]
    eid = _analisada(engine, sinais=sinais)
    r = qualificar_e_gravar(engine, eid)

    # Fit 90·0,3 + Intenção 60·0,25 + Gravidade 90·0,2 + Educação 90·0,15 = 27 + 15 + 18 + 13,5
    assert (r.qualificacao.score, r.qualificacao.faixa) == (74, "quente")
    assert r.novo_estado == "MAPEANDO_DECISORES"
    assert tuple(_estado(engine, eid)) == ("MAPEANDO_DECISORES", 74)
    with engine.connect() as conn:
        linha = conn.execute(select(qualificacoes).where(qualificacoes.c.empresa_id == eid)).one()
        acao = conn.execute(select(acoes_agentes).where(acoes_agentes.c.empresa_id == eid)).one()
        evento = conn.execute(select(eventos).where(eventos.c.empresa_id == eid)).one()
    assert linha.faixa == "quente" and len(linha.componentes_json) == 5
    assert (acao.agente, acao.modelo, acao.custo) == ("qualificador", "regra-v1", Decimal("0.0000"))
    assert evento.tipo == "qualificado"
    assert "score 74 de 100, Quente" in evento.dados_json["mensagem"]


def test_frio_fica_em_qualificando(engine):
    eid = _analisada(engine, setor="outro", nota=95)
    r = qualificar_e_gravar(engine, eid)
    assert r.qualificacao.faixa == "frio"
    assert r.novo_estado is None
    assert _estado(engine, eid).estado == "QUALIFICANDO"


def test_recalcular_nao_volta_a_empresa_de_estado(engine):
    eid = _analisada(engine, setor="outro", nota=95, estado="MAPEANDO_DECISORES")
    r = qualificar_e_gravar(engine, eid)
    assert r.qualificacao.faixa == "frio"
    assert _estado(engine, eid).estado == "MAPEANDO_DECISORES"


def test_sem_auditoria_analisada_nao_qualifica(engine):
    eid = inserir_empresa(engine, estado="QUALIFICANDO")
    assert qualificar_e_gravar(engine, eid) is None


def test_config_do_banco_e_usada(engine):
    eid = _analisada(engine)
    with engine.begin() as conn:
        conn.execute(config.insert().values(chave="score_faixas", valor_json={"quente": 95, "morno": 90}))
    assert qualificar_e_gravar(engine, eid).qualificacao.faixa == "frio"


def test_orquestrador_qualifica_quem_ja_estava_em_qualificando(engine):
    ctx = montar_ctx(engine, ia=None)
    quente = _analisada(engine)
    assert asyncio.run(processar_empresa(ctx, str(quente))) == "qualificado"
    assert _estado(engine, quente).estado == "MAPEANDO_DECISORES"
    # Frio fica em QUALIFICANDO; reenviar não recalcula nem duplica
    frio = _analisada(engine, setor="outro", nota=95)
    assert asyncio.run(processar_empresa(ctx, str(frio))) == "qualificado"
    assert asyncio.run(processar_empresa(ctx, str(frio))) == "ja_qualificada"


def test_config_invalida_vira_evento_e_nao_quebra_o_job(engine):
    eid = _analisada(engine)
    with engine.begin() as conn:
        conn.execute(config.insert().values(chave="score_pesos", valor_json={**PESOS_PADRAO, "fit_icp": 0.9}))
    ctx = montar_ctx(engine, ia=None)
    assert asyncio.run(processar_empresa(ctx, str(eid))) == "qualificacao_falhou"
    with engine.connect() as conn:
        tipos = [r.tipo for r in conn.execute(select(eventos.c.tipo).where(eventos.c.empresa_id == eid))]
    assert tipos == ["qualificacao_falhou"]
