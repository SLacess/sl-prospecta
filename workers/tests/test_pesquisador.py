import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from slp_workers.agents.researcher import (
    CandidatoDominio,
    Dossie,
    ResolucaoDominio,
    carregar_prompt,
    validar_fontes,
    verificar_candidatos,
)
from slp_workers.llm import calcular_consumo, extrair_json
from slp_workers.settings import WorkerConfig
from tests.conftest import ESG, HOME, SOBRE, dossie_exemplo

ESQUEMA = Path(__file__).resolve().parents[2] / "packages" / "schemas" / "dossie.schema.json"


# --- Custo -------------------------------------------------------------------


def test_custo_em_reais_com_busca_na_web():
    usage = SimpleNamespace(
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=3),
    )
    c = calcular_consumo("claude-sonnet-5-5", usage, WorkerConfig(usd_brl_rate=Decimal("5.50")))
    # US$ 2,00 entrada + US$ 1,00 saída + 3 buscas × US$ 0,01 = US$ 3,03
    assert c.custo_usd == Decimal("3.03")
    assert c.custo_brl == Decimal("16.6650")
    assert (c.tokens_in, c.tokens_out, c.buscas_web) == (1_000_000, 100_000, 3)


def test_cache_entra_com_desconto_e_modelo_desconhecido_nao_subestima():
    usage = SimpleNamespace(
        input_tokens=0,
        output_tokens=0,
        cache_read_input_tokens=1_000_000,
        cache_creation_input_tokens=0,
        server_tool_use=None,
    )
    assert calcular_consumo("claude-sonnet-5-5", usage, WorkerConfig()).custo_usd == Decimal("0.2")
    caro = calcular_consumo(
        "modelo-novo", SimpleNamespace(input_tokens=1_000_000, output_tokens=0), WorkerConfig()
    )
    assert caro.custo_usd == Decimal("4")  # preço do mais caro da tabela (Opus)


def test_extrai_o_ultimo_json_do_texto():
    texto = 'Pesquisei.\n```json\n{"candidatos": [], "raciocinio_resumido": "nada"}\n```'
    assert extrair_json(texto)["raciocinio_resumido"] == "nada"
    with pytest.raises(ValueError):
        extrair_json("sem json aqui")


# --- Resolução de domínio ----------------------------------------------------


def _candidato(dominio, confianca="alta"):
    return CandidatoDominio(
        dominio=dominio, nome_oficial="X", evidencia_url=f"https://{dominio}/", confianca=confianca
    )


def test_so_aceita_dominio_que_apareceu_na_busca():
    resolucao = ResolucaoDominio(
        candidatos=[
            _candidato("www.exemplo.com.br"),
            _candidato("inventado.com.br"),
            _candidato("exemplo.com.br"),
        ],
        raciocinio_resumido="",
    )
    verificados = verificar_candidatos(
        resolucao, ["https://www.exemplo.com.br/sobre", "https://g1.globo.com/x"]
    )
    assert [c.dominio for c in verificados] == ["exemplo.com.br"]


# --- Dossiê ------------------------------------------------------------------


def test_descarta_o_que_cita_pagina_nao_lida():
    dossie = dossie_exemplo(
        mencoes_inclusao=dossie_exemplo().mencoes_inclusao
        + [
            dossie_exemplo()
            .mencoes_inclusao[0]
            .model_copy(update={"url": "https://exemplo.com.br/inventada"})
        ],
        resumo_5_linhas=["a", "b", " ", "c", "d", "e", "f"],
    )
    validado, removidos = validar_fontes(dossie, [HOME, SOBRE, ESG])
    assert removidos == 1
    assert len(validado.mencoes_inclusao) == 1
    assert len(validado.sinais) == 1  # ESG com barra final conta como a mesma página
    assert validado.localizacao.cidade == "Sorocaba"
    assert validado.resumo_5_linhas == ["a", "b", "c", "d", "e"]
    assert any("descartada" in lacuna for lacuna in validado.lacunas)


def test_localizacao_sem_fonte_e_apagada():
    dossie = dossie_exemplo(
        localizacao=dossie_exemplo().localizacao.model_copy(update={"url": "https://outro/x"})
    )
    validado, _ = validar_fontes(dossie, [HOME])
    assert validado.localizacao.cidade is None


def test_esquema_publicado_esta_atualizado():
    """packages/schemas/dossie.schema.json é gerado do modelo Pydantic (prompts são código, §18)."""
    assert json.loads(ESQUEMA.read_text(encoding="utf-8")) == Dossie.model_json_schema()


def test_prompts_carregam_sem_o_cabecalho():
    texto = carregar_prompt("researcher")
    assert texto.startswith("Você é o Pesquisador")
    assert "versao:" not in texto
    assert "somente como dado" in texto  # proteção contra instruções vindas do site
    assert carregar_prompt("researcher-dominio").startswith("Você ajuda")
