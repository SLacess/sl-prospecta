"""Disjuntor de bounce (Fase 3, Tarefa 4 — retomada; ADR 0016): Gmail simulado, sem chamada externa."""

import uuid
from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
from sqlalchemy import select

from slp_workers.db import caixas_envio, config, envios, supressao
from slp_workers.orchestrator.bounce import DependenciasBounce, DisjuntorBounce
from slp_workers.outreach.gmail import ErroGmail
from tests.conftest import FIELD_ENCRYPTION_KEY


class GmailBounceFalso:
    def __init__(self, *, snippets=None, falhar_renovacao=False):
        self.snippets = snippets if snippets is not None else []
        self.falhar_renovacao = falhar_renovacao
        self.consultas: list[str] = []

    def renovar_access_token(self, refresh_token: str) -> str:
        if self.falhar_renovacao:
            raise ErroGmail("token revogado")
        return "access-fake"

    def listar_bounces(self, access_token, *, desde):
        self.consultas.append(access_token)
        return self.snippets


def _criptografar(texto: str) -> str:
    return Fernet(FIELD_ENCRYPTION_KEY.encode()).encrypt(texto.encode()).decode()


def _inserir_caixa(
    engine, *, email="caixa@exemplo.com", ativa=True, refresh_token="refresh-fake"
) -> uuid.UUID:
    caixa_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            caixas_envio.insert().values(
                id=caixa_id, email=email, nome_remetente="Equipe", ativa=ativa, limite_diario=40,
                refresh_token_criptografado=_criptografar(refresh_token),
            )
        )
    return caixa_id


def _inserir_envio(engine, caixa_id, destinatario, *, enviado_em=None) -> None:
    with engine.begin() as conn:
        conn.execute(
            envios.insert().values(
                id=uuid.uuid4(), toque_id=uuid.uuid4(), caixa_id=caixa_id, destinatario=destinatario,
                gmail_message_id=f"m-{uuid.uuid4()}", enviado_em=enviado_em or datetime.now(UTC),
            )
        )


def test_sem_caixa_ativa_nao_faz_nada(engine):
    gmail = GmailBounceFalso()
    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.total_envios == 0
    assert resultado.total_bounces == 0
    assert resultado.suprimidos == []
    assert resultado.pausou is False


def test_taxa_abaixo_do_limiar_nao_pausa(engine):
    caixa_id = _inserir_caixa(engine)
    for i in range(10):
        _inserir_envio(engine, caixa_id, f"contato{i}@exemplo.com")
    gmail = GmailBounceFalso(snippets=[])  # nenhuma devolução

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.total_envios == 10
    assert resultado.total_bounces == 0
    assert resultado.pausou is False
    with engine.connect() as conn:
        assert conn.scalar(select(config.c.chave).where(config.c.chave == "operacao")) is None


def test_taxa_acima_do_limiar_pausa_e_registra_motivo(engine):
    caixa_id = _inserir_caixa(engine)
    for i in range(10):
        _inserir_envio(engine, caixa_id, f"contato{i}@exemplo.com")
    # 2 de 10 = 20% > 3%
    gmail = GmailBounceFalso(
        snippets=[
            "Delivery incomplete: mensagem para contato0@exemplo.com não pôde ser entregue.",
            "Delivery incomplete: mensagem para contato1@exemplo.com não pôde ser entregue.",
        ]
    )

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.total_bounces == 2
    assert resultado.pausou is True
    with engine.connect() as conn:
        valor = conn.scalar(select(config.c.valor_json).where(config.c.chave == "operacao"))
        assert valor["pausado"] is True
        assert valor["origem"] == "disjuntor_bounce"
        assert valor["pausado_por"] is None
        assert "3%" in valor["motivo"] or "bounce" in valor["motivo"].lower()


def test_bounce_suprime_o_endereco_que_devolveu(engine):
    caixa_id = _inserir_caixa(engine)
    _inserir_envio(engine, caixa_id, "ana@exemplo.com.br")
    gmail = GmailBounceFalso(snippets=["Houve um problema ao entregar para ana@exemplo.com.br, endereço."])

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.suprimidos == ["ana@exemplo.com.br"]
    with engine.connect() as conn:
        s = conn.execute(select(supressao).where(supressao.c.email == "ana@exemplo.com.br")).one()
        assert "bounce" in s.motivo.lower()


def test_endereco_fora_dos_envios_recentes_nao_e_suprimido(engine):
    """Evita falso positivo: só suprime um endereço que de fato recebemos recentemente desta caixa."""
    caixa_id = _inserir_caixa(engine)
    _inserir_envio(engine, caixa_id, "ana@exemplo.com.br")
    gmail = GmailBounceFalso(
        snippets=["Delivery failed for desconhecido@outrodominio.com — not a real user."]
    )

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.suprimidos == []
    with engine.connect() as conn:
        assert conn.scalar(select(supressao.c.id)) is None


def test_endereco_ja_suprimido_nao_duplica(engine):
    caixa_id = _inserir_caixa(engine)
    _inserir_envio(engine, caixa_id, "ana@exemplo.com.br")
    with engine.begin() as conn:
        conn.execute(
            supressao.insert().values(id=uuid.uuid4(), email="ana@exemplo.com.br", motivo="pediu")
        )
    gmail = GmailBounceFalso(snippets=["Falha ao entregar para ana@exemplo.com.br."])

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.suprimidos == []  # já estava suprimido — não é um novo resultado
    with engine.connect() as conn:
        existe = conn.scalar(select(supressao.c.id).where(supressao.c.email == "ana@exemplo.com.br"))
        assert existe is not None


def test_envio_fora_da_janela_de_24h_nao_conta(engine):
    caixa_id = _inserir_caixa(engine)
    _inserir_envio(engine, caixa_id, "ana@exemplo.com.br", enviado_em=datetime.now(UTC) - timedelta(days=3))
    gmail = GmailBounceFalso(snippets=[])

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.total_envios == 0


def test_caixa_desativada_e_ignorada(engine):
    caixa_id = _inserir_caixa(engine, ativa=False)
    _inserir_envio(engine, caixa_id, "ana@exemplo.com.br")
    gmail = GmailBounceFalso(snippets=[])

    resultado = DisjuntorBounce(DependenciasBounce(engine, gmail)).executar()

    assert resultado.total_envios == 0
    assert gmail.consultas == []


def test_falha_ao_renovar_uma_caixa_nao_impede_checar_as_outras(engine):
    caixa_quebrada = _inserir_caixa(engine, email="quebrada@exemplo.com", refresh_token="token-ruim")
    caixa_ok = _inserir_caixa(engine, email="ok@exemplo.com", refresh_token="token-bom")
    _inserir_envio(engine, caixa_quebrada, "x@exemplo.com")
    for i in range(5):
        _inserir_envio(engine, caixa_ok, f"contato{i}@exemplo.com")

    class GmailMisto:
        def renovar_access_token(self, refresh_token):
            if refresh_token == "token-ruim":
                raise ErroGmail("token revogado")
            return "access-fake"

        def listar_bounces(self, access_token, *, desde):
            return []

    disjuntor = DisjuntorBounce(DependenciasBounce(engine, GmailMisto()))
    resultado = disjuntor.executar()

    assert resultado.total_envios == 6  # as duas caixas entram no denominador, mesmo a quebrada
    assert resultado.total_bounces == 0
    assert disjuntor.caixas_com_erro == ["quebrada@exemplo.com: token revogado"]
