"""Mensageiro (Fase 3, Tarefa 3 — retomada; ADR 0016): Gmail e Claude simulados, sem chamada externa."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from slp_workers.agents.guardiao import AvaliacaoGuardiao
from slp_workers.db import caixas_envio, contatos, envios, eventos, sequencias, toques
from slp_workers.llm import Consumo
from slp_workers.orchestrator.mensageiro import DependenciasMensageiro, Mensageiro
from slp_workers.outreach.gmail import ErroGmail
from slp_workers.settings import WorkerConfig
from tests.conftest import FIELD_ENCRYPTION_KEY, inserir_empresa

REFRESH_PLANO = "refresh-fake"


class IAFalsa:
    """Só usada quando o Guardião ainda não avaliou o toque — a maioria dos testes já grava o resultado."""

    def __init__(self, aprovado: bool = True):
        self.avaliacao = AvaliacaoGuardiao(
            aprovado=aprovado, motivo="Identificação e opt-out conferem.", raciocinio_resumido="Ok."
        )
        self.chamadas = 0

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        self.chamadas += 1
        return self.avaliacao, Consumo(modelo=modelo, custo_brl=Decimal("0.01"))


class GmailFalso:
    def __init__(self, *, falhar_renovacao=False, falhar_envio=False, message_id="msg-1"):
        self.falhar_renovacao = falhar_renovacao
        self.falhar_envio = falhar_envio
        self.message_id = message_id
        self.renovacoes: list[str] = []
        self.envios: list[dict] = []

    def renovar_access_token(self, refresh_token: str) -> str:
        self.renovacoes.append(refresh_token)
        if self.falhar_renovacao:
            raise ErroGmail("token revogado")
        return "access-fake"

    def enviar(self, access_token, *, remetente_nome, remetente_email, destinatario, assunto, corpo):
        self.envios.append(
            {"remetente": remetente_email, "destinatario": destinatario, "assunto": assunto, "corpo": corpo}
        )
        if self.falhar_envio:
            raise ErroGmail("Gmail fora do ar")
        return self.message_id


@pytest.fixture
def config():
    return WorkerConfig()


def _criptografar(texto: str) -> str:
    return Fernet(FIELD_ENCRYPTION_KEY.encode()).encrypt(texto.encode()).decode()


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


def _inserir_toque(
    engine, empresa_id, contato_id, *, dia=0, canal="email", decisao_humana="aprovado",
    enviado_em=None, guardiao_resultado="aprovado",
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
                id=toque_id, sequencia_id=seq_id, dia=dia, canal=canal, status="rascunho",
                conteudo_sugerido="x", assunto="assunto original", corpo="corpo original",
                assunto_final="Assunto final", corpo_final="Corpo final, com opt-out.",
                decisao_humana=decisao_humana, enviado_em=enviado_em, guardiao_resultado=guardiao_resultado,
                guardiao_avaliado_em=datetime.now(UTC) if guardiao_resultado else None,
                criado_em=datetime.now(UTC),
            )
        )
    return toque_id


def _inserir_caixa(
    engine, *, email="caixa@prospeccao.exemplo.com.br", ativa=True, limite_diario=40,
    refresh_token=REFRESH_PLANO,
) -> uuid.UUID:
    caixa_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            caixas_envio.insert().values(
                id=caixa_id, email=email, nome_remetente="Equipe Sinal Link",
                refresh_token_criptografado=_criptografar(refresh_token), ativa=ativa,
                limite_diario=limite_diario,
            )
        )
    return caixa_id


def _deps(engine, config, gmail=None, ia=None) -> DependenciasMensageiro:
    return DependenciasMensageiro(
        engine=engine, ia=ia or IAFalsa(), config=config, gmail=gmail or GmailFalso()
    )


def test_nada_a_fazer_se_nao_aprovado(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id, decisao_humana=None, guardiao_resultado=None)

    resultado = asyncio.run(Mensageiro(_deps(engine, config), toque_id).executar())

    assert resultado is None


def test_nada_a_fazer_se_ja_enviado(engine, config):
    empresa_id = inserir_empresa(engine, estado="EM_SEQUENCIA")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id, enviado_em=datetime.now(UTC))

    resultado = asyncio.run(Mensageiro(_deps(engine, config), toque_id).executar())

    assert resultado is None


def test_nada_a_fazer_se_canal_nao_e_email(engine, config):
    empresa_id = inserir_empresa(engine, estado="EM_SEQUENCIA")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id, dia=5, canal="linkedin")
    _inserir_caixa(engine)

    resultado = asyncio.run(Mensageiro(_deps(engine, config), toque_id).executar())

    assert resultado is None


def test_bloqueado_pelo_guardiao_nao_envia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id, guardiao_resultado="bloqueado")
    _inserir_caixa(engine)
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "bloqueado_pelo_guardiao"
    assert gmail.envios == []


def test_guardiao_ainda_nao_avaliado_e_chamado_antes_de_enviar(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id, guardiao_resultado=None)
    _inserir_caixa(engine)
    ia = IAFalsa(aprovado=True)
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail, ia=ia), toque_id).executar())

    assert resultado == "enviado"
    assert ia.chamadas == 1
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.guardiao_resultado == "aprovado"


def test_sem_caixa_ativa_nao_envia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "sem_caixa_disponivel"
    assert gmail.envios == []


def test_caixa_no_limite_diario_nao_e_usada(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    caixa_id = _inserir_caixa(engine, limite_diario=1)
    outro_toque_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            envios.insert().values(
                id=uuid.uuid4(), toque_id=outro_toque_id, caixa_id=caixa_id,
                destinatario="outro@exemplo.com", gmail_message_id="msg-0", enviado_em=datetime.now(UTC),
            )
        )
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "sem_caixa_disponivel"


def test_envio_de_ontem_nao_conta_no_limite_de_hoje(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    caixa_id = _inserir_caixa(engine, limite_diario=1)
    outro_toque_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            envios.insert().values(
                id=uuid.uuid4(), toque_id=outro_toque_id, caixa_id=caixa_id,
                destinatario="outro@exemplo.com", gmail_message_id="msg-0",
                enviado_em=datetime.now(UTC) - timedelta(days=2),
            )
        )
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "enviado"


def test_caixa_desativada_nao_e_usada(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id, email="ana@exemplo.com.br")
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    _inserir_caixa(engine, ativa=False)
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "sem_caixa_disponivel"


def test_envio_com_sucesso_grava_envio_toque_e_evento_e_entra_em_sequencia(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id, email="ana@exemplo.com.br")
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    caixa_id = _inserir_caixa(engine, email="caixa@prospeccao.exemplo.com.br")
    gmail = GmailFalso(message_id="msg-123")

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "enviado"
    assert gmail.renovacoes == [REFRESH_PLANO]
    assert gmail.envios[0]["destinatario"] == "ana@exemplo.com.br"
    assert gmail.envios[0]["remetente"] == "caixa@prospeccao.exemplo.com.br"

    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.enviado_em is not None  # `enviado_por` (só no banco da API) fica nulo: enviou o sistema

        envio = conn.execute(select(envios).where(envios.c.toque_id == toque_id)).one()
        assert envio.caixa_id == caixa_id
        assert envio.gmail_message_id == "msg-123"

        from slp_workers.db import empresas

        empresa = conn.execute(select(empresas).where(empresas.c.id == empresa_id)).one()
        assert empresa.estado == "EM_SEQUENCIA"

        tipos = {e.tipo for e in conn.execute(select(eventos))}
        assert tipos == {"toque_enviado", "entrou_em_sequencia"}


def test_segundo_contato_da_mesma_empresa_nao_repete_entrou_em_sequencia(engine, config):
    empresa_id = inserir_empresa(engine, estado="EM_SEQUENCIA")
    contato_id = _inserir_contato(engine, empresa_id, email="beto@exemplo.com.br")
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    _inserir_caixa(engine)

    resultado = asyncio.run(Mensageiro(_deps(engine, config), toque_id).executar())

    assert resultado == "enviado"
    with engine.connect() as conn:
        tipos = [e.tipo for e in conn.execute(select(eventos))]
        assert "entrou_em_sequencia" not in tipos


def test_rodizio_usa_a_caixa_com_menos_envios_hoje(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    caixa_cheia = _inserir_caixa(engine, email="cheia@exemplo.com", limite_diario=5)
    caixa_livre = _inserir_caixa(engine, email="livre@exemplo.com", limite_diario=5)
    with engine.begin() as conn:
        for _ in range(3):
            conn.execute(
                envios.insert().values(
                    id=uuid.uuid4(), toque_id=uuid.uuid4(), caixa_id=caixa_cheia,
                    destinatario="x@exemplo.com", gmail_message_id=f"m-{uuid.uuid4()}",
                    enviado_em=datetime.now(UTC),
                )
            )
    gmail = GmailFalso()

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "enviado"
    assert gmail.envios[0]["remetente"] == "livre@exemplo.com"
    with engine.connect() as conn:
        envio = conn.execute(select(envios).where(envios.c.toque_id == toque_id)).one()
        assert envio.caixa_id == caixa_livre


def test_falha_ao_renovar_marca_erro_na_caixa_e_nao_tenta_de_novo_no_lote(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque1 = _inserir_toque(engine, empresa_id, contato_id, dia=0)
    contato2_id = _inserir_contato(engine, empresa_id, email="outro@exemplo.com.br")
    toque2 = _inserir_toque(engine, empresa_id, contato2_id, dia=0)
    _inserir_caixa(engine)
    gmail = GmailFalso(falhar_renovacao=True)
    deps = _deps(engine, config, gmail=gmail)

    r1 = asyncio.run(Mensageiro(deps, toque1).executar())
    r2 = asyncio.run(Mensageiro(deps, toque2).executar())

    assert r1 == "erro_de_caixa"
    assert r2 == "sem_caixa_disponivel"  # já marcada como inválida neste lote — não tenta de novo
    assert len(gmail.renovacoes) == 1
    with engine.connect() as conn:
        caixa = conn.execute(select(caixas_envio)).one()
        assert caixa.erro_verificacao is not None
        assert "reconecte" in caixa.erro_verificacao.lower()


def test_falha_no_envio_registra_evento_e_mantem_toque_pendente(engine, config):
    empresa_id = inserir_empresa(engine, estado="PREPARANDO_ABORDAGEM")
    contato_id = _inserir_contato(engine, empresa_id)
    toque_id = _inserir_toque(engine, empresa_id, contato_id)
    _inserir_caixa(engine)
    gmail = GmailFalso(falhar_envio=True)

    resultado = asyncio.run(Mensageiro(_deps(engine, config, gmail=gmail), toque_id).executar())

    assert resultado == "erro_de_envio"
    with engine.connect() as conn:
        t = conn.execute(select(toques).where(toques.c.id == toque_id)).one()
        assert t.enviado_em is None
        tipos = {e.tipo for e in conn.execute(select(eventos))}
        assert tipos == {"envio_falhou"}
