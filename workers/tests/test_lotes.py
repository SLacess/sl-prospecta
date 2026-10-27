"""Mapeamento de colunas de planilha com IA (Fase 2, Tarefa 3). Claude simulado."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from slp_workers.agents.mapeador_colunas import MapeamentoColunas, combinar, validar
from slp_workers.db import acoes_agentes, lotes
from slp_workers.llm import Consumo, ErroIA
from slp_workers.orchestrator.lotes import AVISO_SEM_IA, mapear_colunas_lote

COLUNAS = [
    {"indice": 0, "cabecalho": "Coluna X", "exemplos": ["Hospital A"]},
    {"indice": 1, "cabecalho": "Coluna Y", "exemplos": ["hospital-a.com.br"]},
    {"indice": 2, "cabecalho": "Coluna Z", "exemplos": ["a***@hospital-a.com.br"]},
]
VAZIO = dict.fromkeys(
    ("empresa", "site", "cnpj", "cidade", "uf", "contato_nome", "contato_cargo", "contato_email")
)


class IAColunas:
    def __init__(self, resposta: dict | None = None, erro: bool = False):
        self.resposta = resposta
        self.erro = erro
        self.conteudos: list[str] = []

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        self.conteudos.append(conteudo)
        if self.erro:
            raise ErroIA("Claude API indisponível", transitorio=True)
        return MapeamentoColunas(**{**VAZIO, **self.resposta, "raciocinio_resumido": "ok"}), Consumo(
            modelo=modelo, tokens_in=300, tokens_out=60, custo_brl=Decimal("0.0005")
        )


def _lote(engine, status="mapeando", mapa=None):
    lid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            lotes.insert().values(
                id=lid, status=status, mapeamento_json=mapa or dict(VAZIO), mapeamento_origem="regras"
            )
        )
    return lid


def _ler(engine, lid):
    with engine.connect() as conn:
        return conn.execute(select(lotes).where(lotes.c.id == lid)).one()


def test_ia_identifica_as_colunas_e_o_lote_vai_para_a_previa(engine):
    lid = _lote(engine)
    ia = IAColunas({"empresa": 0, "site": 1, "contato_email": 2})
    assert asyncio.run(mapear_colunas_lote({"engine": engine, "ia": ia}, str(lid), COLUNAS)) == "mapeado"
    lote = _ler(engine, lid)
    assert lote.status == "aguardando_confirmacao" and lote.mapeamento_origem == "ia"
    assert (lote.mapeamento_json["empresa"], lote.mapeamento_json["site"]) == (0, 1)
    assert "a***@hospital-a.com.br" in ia.conteudos[0]  # a IA só vê e-mails mascarados
    with engine.connect() as conn:
        acao = conn.execute(select(acoes_agentes)).one()
    assert (
        acao.agente == "mapeador_colunas"
        and acao.empresa_id is None
        and acao.saida_json["lote_id"] == str(lid)
    )


def test_indice_fora_da_planilha_ou_repetido_e_descartado():
    mapa = MapeamentoColunas(**{**VAZIO, "empresa": 0, "site": 0, "cnpj": 7, "raciocinio_resumido": "."})
    validado, descartados = validar(mapa, 3)
    assert (validado["empresa"], validado["site"], validado["cnpj"], descartados) == (0, None, None, 2)


def test_regras_prevalecem_e_a_ia_so_completa():
    regras = {**VAZIO, "site": 1}
    ia = {**VAZIO, "site": 2, "empresa": 0, "cnpj": 1}
    final = combinar(regras, ia)
    assert (final["site"], final["empresa"], final["cnpj"]) == (1, 0, None)  # coluna 1 já é do site


def test_falha_da_ia_fica_com_as_regras_e_avisa(engine):
    lid = _lote(engine, mapa={**VAZIO, "site": 1})
    r = asyncio.run(mapear_colunas_lote({"engine": engine, "ia": IAColunas(erro=True)}, str(lid), COLUNAS))
    assert r == "falhou"
    lote = _ler(engine, lid)
    assert lote.status == "aguardando_confirmacao" and lote.mapeamento_origem == "regras"
    assert lote.resumo_json["aviso_mapeamento"] == AVISO_SEM_IA


def test_teto_de_custo_atingido_nao_chama_a_ia(engine):
    lid = _lote(engine)
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(
                id=uuid.uuid4(),
                agente="x",
                empresa_id=None,
                entrada_hash="x",
                saida_json={},
                modelo="m",
                tokens_in=0,
                tokens_out=0,
                custo=Decimal("999"),
                duracao_ms=0,
                creditos=0,
                criado_em=datetime.now(UTC),
            )
        )
    ia = IAColunas({"empresa": 0})
    assert (
        asyncio.run(mapear_colunas_lote({"engine": engine, "ia": ia}, str(lid), COLUNAS)) == "sem_orcamento"
    )
    assert ia.conteudos == [] and _ler(engine, lid).status == "aguardando_confirmacao"


def test_lote_ja_ajustado_ou_cancelado_nao_e_sobrescrito(engine):
    lid = _lote(engine, status="cancelado")
    ia = IAColunas({"empresa": 0})
    assert asyncio.run(mapear_colunas_lote({"engine": engine, "ia": ia}, str(lid), COLUNAS)) == "ignorado"
    assert ia.conteudos == []


def test_esquema_publicado_esta_atualizado():
    esquema = Path(__file__).resolve().parents[2] / "packages" / "schemas" / "mapeador-colunas.schema.json"
    assert json.loads(esquema.read_text(encoding="utf-8")) == MapeamentoColunas.model_json_schema()
