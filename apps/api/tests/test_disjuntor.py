from datetime import UTC, datetime
from decimal import Decimal

from app.budget import inicio_do_dia, verificar_disjuntor
from app.models import AcaoAgente

# 24/10/2026 10h00 em Brasília (UTC-3) = 13h00 UTC; o dia começou às 03h00 UTC
AGORA = datetime(2026, 10, 24, 13, 0, tzinfo=UTC)


def _acao(db, custo, criado_em):
    db.add(AcaoAgente(agente="teste", entrada_hash="x" * 64, saida_json={}, custo=Decimal(custo),
                      criado_em=criado_em))
    db.commit()


def test_inicio_do_dia_no_fuso_de_brasilia():
    assert inicio_do_dia(AGORA) == datetime(2026, 10, 24, 3, 0, tzinfo=UTC)


def test_soma_so_o_custo_de_hoje(db):
    _acao(db, "20.00", datetime(2026, 10, 24, 2, 59, tzinfo=UTC))  # 23h59 de ontem em Brasília
    _acao(db, "12.50", datetime(2026, 10, 24, 3, 1, tzinfo=UTC))
    _acao(db, "5.25", datetime(2026, 10, 24, 12, 0, tzinfo=UTC))

    d = verificar_disjuntor(db, AGORA)
    assert d.custo_hoje_brl == Decimal("17.75")
    assert d.teto_brl == Decimal("30")
    assert d.atingido is False


def test_dispara_ao_atingir_o_teto(db):
    _acao(db, "29.99", datetime(2026, 10, 24, 10, 0, tzinfo=UTC))
    assert verificar_disjuntor(db, AGORA).atingido is False
    _acao(db, "0.01", datetime(2026, 10, 24, 11, 0, tzinfo=UTC))
    assert verificar_disjuntor(db, AGORA).atingido is True


def test_sem_acoes_custo_zero(db):
    d = verificar_disjuntor(db, AGORA)
    assert d.custo_hoje_brl == Decimal("0.00")
    assert d.atingido is False


def test_endpoint_do_painel(client, vendedor_headers):
    r = client.get("/governanca/disjuntores", headers=vendedor_headers)
    assert r.status_code == 200
    custo = r.json()["custo"]
    assert custo["atingido"] is False
    assert Decimal(custo["teto_brl"]) == Decimal("30")
    assert "R$ 0,00 de R$ 30,00" in custo["mensagem"]


def test_endpoint_exige_login(client):
    assert client.get("/governanca/disjuntores").status_code == 401
