"""Geração da sequência (Fase 3, Tarefa 2): Claude simulado, sem nenhuma chamada externa."""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from slp_workers.agents.copywriter import Redacao
from slp_workers.agents.reviewer import CriteriosCritico, Critica
from slp_workers.agents.strategist import Estrategia, Toque
from slp_workers.db import (
    acoes_agentes,
    auditorias,
    contatos,
    dossies,
    eventos,
    sequencias,
    supressao,
    toques,
)
from slp_workers.llm import Consumo
from slp_workers.orchestrator.budget import inicio_do_dia
from slp_workers.orchestrator.sequencia import CustoDiarioEsgotado, DependenciasSequencia, Sequencia
from slp_workers.settings import WorkerConfig
from tests.conftest import inserir_empresa

ESQUEMAS = Path(__file__).resolve().parents[2] / "packages" / "schemas"

ACHADO = {
    "titulo": "Formulário de contato sem rótulo para leitor de tela",
    "impacto_humano": "uma pessoa cega não sabe o que digitar em cada campo",
    "criterio_wcag": "4.1.2",
    "pagina_url": "https://exemplo.com.br/contato",
    "problema": "formulario-sem-rotulo",
}


def estrategia_exemplo(**alteracoes) -> Estrategia:
    base = Estrategia(
        persona="ti",
        angulo="conformidade_legal",
        achado_titulo=ACHADO["titulo"],
        achado_pagina_url=ACHADO["pagina_url"],
        gancho_justificativa="Achado técnico claro para o decisor de TI.",
        canal_e_cadencia=[
            Toque(dia=0, canal="email", conteudo_sugerido="Achado principal"),
            Toque(dia=3, canal="email", conteudo_sugerido="Segundo achado"),
            Toque(dia=8, canal="email", conteudo_sugerido="Insight setorial"),
            Toque(dia=14, canal="email", conteudo_sugerido="Benchmark setorial"),
            Toque(dia=21, canal="email", conteudo_sugerido="Encerramento"),
        ],
        raciocinio_resumido="Ângulo técnico para o decisor de TI.",
    )
    return base.model_copy(update=alteracoes)


def redacao_exemplo(**alteracoes) -> Redacao:
    base = Redacao(
        assunto="formulário de contato sem rótulo",
        corpo="Olá, Ana. " * 5,
        fatos_usados=[f"achado: {ACHADO['titulo']}"],
        angulo="conformidade_legal",
        raciocinio_resumido="Abertura direta no achado técnico.",
    )
    return base.model_copy(update=alteracoes)


def critica_exemplo(aprovado: bool = True, **alteracoes) -> Critica:
    nota = 8 if aprovado else 5
    criterios = CriteriosCritico(
        especificidade=nota,
        veracidade=nota,
        humanidade=nota,
        clareza=nota,
        valor=nota,
        honestidade=nota,
        brevidade=nota,
        acessibilidade=nota,
    )
    base = Critica(
        criterios=criterios,
        nota=nota,
        aprovado=aprovado,
        motivo="Tudo confere." if aprovado else "Veracidade fraca: reescreva citando só o achado recebido.",
        raciocinio_resumido="Resumo da decisão.",
    )
    return base.model_copy(update=alteracoes)


class IASequenciaFalsa:
    """Devolve Estrategia/Redacao/Critica conforme `formato`; Redacao/Critica avançam numa lista fixa
    (índice clampado no último item) para simular o laço de reescrita."""

    def __init__(self, estrategia=None, redacoes=None, criticas=None):
        self.estrategia = estrategia or estrategia_exemplo()
        self.redacoes = redacoes or [redacao_exemplo()]
        self.criticas = criticas or [critica_exemplo(aprovado=True)]
        self.chamadas: list[str] = []
        self._i_redator = 0
        self._i_critico = 0

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        self.chamadas.append(formato.__name__)
        if formato is Estrategia:
            return self.estrategia, Consumo(modelo=modelo, custo_brl=Decimal("0.10"))
        if formato is Redacao:
            r = self.redacoes[min(self._i_redator, len(self.redacoes) - 1)]
            self._i_redator += 1
            return r, Consumo(modelo=modelo, custo_brl=Decimal("0.05"))
        if formato is Critica:
            c = self.criticas[min(self._i_critico, len(self.criticas) - 1)]
            self._i_critico += 1
            return c, Consumo(modelo=modelo, custo_brl=Decimal("0.03"))
        raise AssertionError(f"formato inesperado: {formato}")


def _inserir_contato(
    engine,
    empresa_id,
    *,
    nome="Ana Souza",
    area="TI",
    email="ana@exemplo.com.br",
    email_status="valido",
    opt_out=False,
) -> uuid.UUID:
    cid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            contatos.insert().values(
                id=cid,
                empresa_id=empresa_id,
                nome=nome,
                cargo="Gerente de TI",
                area=area,
                email=email,
                email_status=email_status,
                opt_out=opt_out,
                fonte="apollo",
                criado_em=datetime.now(UTC),
            )
        )
    return cid


def _inserir_dossie_e_auditoria(engine, empresa_id, achados=None) -> None:
    with engine.begin() as conn:
        conn.execute(
            dossies.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                dados_json={},
                resumo="Linha 1\nLinha 2\nLinha 3",
                sinais_json={},
                versao=1,
                criado_em=datetime.now(UTC),
            )
        )
        conn.execute(
            auditorias.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_id,
                nota=70,
                totais_json={},
                achados_json={"top3_para_leigos": achados if achados is not None else [ACHADO]},
                paginas_json=[],
                artefatos_urls=[],
                criado_em=datetime.now(UTC),
            )
        )


@pytest.fixture
def config():
    return WorkerConfig()


@pytest.fixture
def empresa_preparando(engine):
    return inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")


def test_caminho_feliz_aprovado_na_primeira_tentativa(engine, config, empresa_preparando):
    contato_id = _inserir_contato(engine, empresa_preparando)
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    ia = IASequenciaFalsa()

    resultado = asyncio.run(
        Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar()
    )

    assert resultado == {str(contato_id): "sequencia_gerada"}
    with engine.connect() as conn:
        seq = conn.execute(select(sequencias).where(sequencias.c.contato_id == contato_id)).one()
        assert seq.persona == "ti" and seq.angulo == "conformidade_legal"
        linhas = conn.execute(select(toques).where(toques.c.sequencia_id == seq.id)).all()
        assert len(linhas) == 5
        dia0 = next(t for t in linhas if t.dia == 0)
        assert dia0.status == "rascunho" and dia0.aprovado is True and dia0.tentativas == 1
        assert all(t.status == "planejada" for t in linhas if t.dia != 0)
        acoes = conn.execute(select(acoes_agentes).where(acoes_agentes.c.contato_id == contato_id)).all()
        assert {a.agente for a in acoes} == {"estrategista", "redator", "critico"}
        tipos = {e.tipo for e in conn.execute(select(eventos).where(eventos.c.contato_id == contato_id))}
        assert tipos == {"sequencia_gerada"}


def test_reescrita_dispara_e_aprova_na_segunda_tentativa(engine, config, empresa_preparando):
    contato_id = _inserir_contato(engine, empresa_preparando)
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    redacao_ruim = redacao_exemplo(corpo="Primeira tentativa, com um fato inventado.")
    redacao_boa = redacao_exemplo(corpo="Segunda tentativa, só com fatos reais.")
    ia = IASequenciaFalsa(
        redacoes=[redacao_ruim, redacao_boa],
        criticas=[critica_exemplo(aprovado=False), critica_exemplo(aprovado=True)],
    )

    asyncio.run(Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar())

    assert ia.chamadas.count("Redacao") == 2
    assert ia.chamadas.count("Critica") == 2
    with engine.connect() as conn:
        seq_id = conn.scalar(select(sequencias.c.id).where(sequencias.c.contato_id == contato_id))
        dia0 = conn.execute(select(toques).where(toques.c.sequencia_id == seq_id, toques.c.dia == 0)).one()
    assert dia0.tentativas == 2
    assert dia0.aprovado is True
    assert dia0.corpo == redacao_boa.corpo  # só o rascunho final fica salvo, não a primeira tentativa


def test_esgota_tres_tentativas_sem_aprovar_mesmo_assim_salva(engine, config, empresa_preparando):
    contato_id = _inserir_contato(engine, empresa_preparando)
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    ia = IASequenciaFalsa(criticas=[critica_exemplo(aprovado=False)])

    asyncio.run(Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar())

    assert ia.chamadas.count("Redacao") == 3
    assert ia.chamadas.count("Critica") == 3
    with engine.connect() as conn:
        seq_id = conn.scalar(select(sequencias.c.id).where(sequencias.c.contato_id == contato_id))
        dia0 = conn.execute(select(toques).where(toques.c.sequencia_id == seq_id, toques.c.dia == 0)).one()
        tipos = {e.tipo for e in conn.execute(select(eventos).where(eventos.c.contato_id == contato_id))}
    assert dia0.status == "rascunho" and dia0.aprovado is False and dia0.tentativas == 3
    assert tipos == {"sequencia_gerada", "sequencia_sem_aprovacao"}


def test_contato_suprimido_e_pulado_sem_chamar_ia(engine, config, empresa_preparando):
    _inserir_contato(engine, empresa_preparando, email="ana@exemplo.com.br")
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    with engine.begin() as conn:
        conn.execute(supressao.insert().values(id=uuid.uuid4(), email="ana@exemplo.com.br", motivo="opt-out"))
    ia = IASequenciaFalsa()

    resultado = asyncio.run(
        Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar()
    )

    assert list(resultado.values()) == ["contato_suprimido"]
    assert ia.chamadas == []
    with engine.connect() as conn:
        assert conn.scalar(select(sequencias.c.id)) is None


def test_dominio_suprimido_nao_chama_ia(engine, config):
    empresa_id = inserir_empresa(engine, dominio="suprimido.com.br", estado="PREPARANDO_ABORDAGEM")
    _inserir_contato(engine, empresa_id)
    with engine.begin() as conn:
        conn.execute(
            supressao.insert().values(id=uuid.uuid4(), dominio="suprimido.com.br", motivo="pediu para sair")
        )
    ia = IASequenciaFalsa()

    resultado = asyncio.run(Sequencia(DependenciasSequencia(engine, ia, config), empresa_id).executar())

    assert resultado == {}
    assert ia.chamadas == []


def test_contato_que_ja_tem_sequencia_e_pulado_outro_segue(engine, config, empresa_preparando):
    c1 = _inserir_contato(engine, empresa_preparando, nome="Ana Souza", area="TI", email="ana@exemplo.com.br")
    c2 = _inserir_contato(
        engine, empresa_preparando, nome="Bruno Lima", area="RH", email="bruno@exemplo.com.br"
    )
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    with engine.begin() as conn:
        conn.execute(
            sequencias.insert().values(
                id=uuid.uuid4(),
                empresa_id=empresa_preparando,
                contato_id=c1,
                persona="ti",
                angulo="conformidade_legal",
                achado_titulo="x",
                achado_pagina_url="https://x",
                gancho_justificativa="x",
                criado_em=datetime.now(UTC),
            )
        )
    ia = IASequenciaFalsa(estrategia=estrategia_exemplo(persona="rh_di", angulo="inclusao_colaboradores_pcd"))

    resultado = asyncio.run(
        Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar()
    )

    assert resultado[str(c1)] == "ja_tem_sequencia"
    assert resultado[str(c2)] == "sequencia_gerada"
    assert "Estrategia" in ia.chamadas  # só chamou a IA para o c2


def test_disjuntor_global_atingido_para_sem_gastar(engine, config, empresa_preparando):
    _inserir_contato(engine, empresa_preparando)
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    with engine.begin() as conn:
        conn.execute(
            acoes_agentes.insert().values(
                id=uuid.uuid4(),
                agente="estrategista",
                empresa_id=empresa_preparando,
                entrada_hash="x",
                saida_json={},
                raciocinio=None,
                modelo="claude-opus-5-5",
                tokens_in=0,
                tokens_out=0,
                custo=config.daily_ai_budget_brl,
                duracao_ms=0,
                creditos=0,
                criado_em=inicio_do_dia(),
            )
        )
    ia = IASequenciaFalsa()

    with pytest.raises(CustoDiarioEsgotado):
        asyncio.run(Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar())
    assert ia.chamadas == []


def test_empresa_fora_de_preparando_abordagem_nao_faz_nada(engine, config):
    empresa_id = inserir_empresa(engine, estado="MAPEANDO_DECISORES")
    _inserir_contato(engine, empresa_id)
    ia = IASequenciaFalsa()

    resultado = asyncio.run(Sequencia(DependenciasSequencia(engine, ia, config), empresa_id).executar())

    assert resultado == {}
    assert ia.chamadas == []


def test_sem_contatos_validos_nao_faz_nada(engine, config, empresa_preparando):
    _inserir_contato(engine, empresa_preparando, email_status="sem_email")
    _inserir_dossie_e_auditoria(engine, empresa_preparando)
    ia = IASequenciaFalsa()

    resultado = asyncio.run(
        Sequencia(DependenciasSequencia(engine, ia, config), empresa_preparando).executar()
    )

    assert resultado == {}
    assert ia.chamadas == []


def test_esquemas_publicados_estao_atualizados():
    assert json.loads((ESQUEMAS / "estrategia.schema.json").read_text(encoding="utf-8")) == (
        Estrategia.model_json_schema()
    )
    assert json.loads((ESQUEMAS / "redacao.schema.json").read_text(encoding="utf-8")) == (
        Redacao.model_json_schema()
    )
    assert json.loads((ESQUEMAS / "critica.schema.json").read_text(encoding="utf-8")) == (
        Critica.model_json_schema()
    )


def test_prompts_proibem_promessa_de_conformidade_total():
    from slp_workers.agents.researcher import carregar_prompt

    for nome in ("strategist", "copywriter", "reviewer", "voz-sinal-link"):
        texto = carregar_prompt(nome)
        if "100% acessível" in texto or "garantimos conformidade" in texto:
            # a proibição em si menciona a frase — confere que é proibição, não instrução de uso
            assert "proib" in texto.lower() or "nunca" in texto.lower()
