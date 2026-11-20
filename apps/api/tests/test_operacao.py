"""Disjuntores de envio e "Pausar tudo" (CONSTITUICAO §13; ADR 0016, Tarefa 4)."""


def test_estado_inicial_nao_pausado(client, vendedor_headers):
    r = client.get("/operacao", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "pausado": False, "motivo": None, "pausado_em": None, "pausado_por_nome": None, "origem": None,
    }


def test_vendedor_pode_pausar(client, vendedor_headers):
    r = client.post(
        "/operacao/pausar", json={"motivo": "Caixa recebeu reclamação."}, headers=vendedor_headers
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["pausado"] is True
    assert corpo["motivo"] == "Caixa recebeu reclamação."
    assert corpo["origem"] == "manual"
    assert corpo["pausado_por_nome"] == "vendedor"
    assert corpo["pausado_em"] is not None


def test_leitura_nao_pode_pausar(client, leitura_headers):
    r = client.post("/operacao/pausar", json={"motivo": "x"}, headers=leitura_headers)
    assert r.status_code == 403


def test_pausar_com_motivo_vazio_e_422(client, vendedor_headers):
    r = client.post("/operacao/pausar", json={"motivo": "  "}, headers=vendedor_headers)
    assert r.status_code == 422


def test_reportar_spam_pausa_com_origem_propria(client, vendedor_headers):
    r = client.post("/operacao/reportar-spam", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["pausado"] is True
    assert corpo["origem"] == "spam_reportado"


def test_vendedor_nao_pode_retomar(client, vendedor_headers):
    client.post("/operacao/pausar", json={"motivo": "x"}, headers=vendedor_headers)
    r = client.post("/operacao/retomar", headers=vendedor_headers)
    assert r.status_code == 403


def test_admin_retoma(client, vendedor_headers, admin_headers):
    client.post("/operacao/pausar", json={"motivo": "x"}, headers=vendedor_headers)
    r = client.post("/operacao/retomar", headers=admin_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["pausado"] is False
    assert corpo["motivo"] is None

    r2 = client.get("/operacao", headers=vendedor_headers)
    assert r2.json()["pausado"] is False
