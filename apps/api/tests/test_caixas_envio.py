"""Caixas de envio conectadas (ADR 0016 — retomada da Fase 3, Tarefa 4).

O client do Google é substituído por um dublê (`ClienteGoogleFalso`), no mesmo espírito do
`httpx.MockTransport` usado para o Apollo no worker: nenhum teste aqui fala com o Google de verdade.
"""

import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from app.google_oauth import ErroGoogleOAuth, get_google_oauth_client
from app.main import app
from app.models import CaixaEnvio
from app.security import criar_state_oauth


class ClienteGoogleFalso:
    def __init__(self, *, configurado=True, tokens=None, email="caixa@prospeccao.exemplo.com.br",
                 falhar_troca=False):
        self.configurado = configurado
        self._tokens = tokens or {
            "access_token": "access-fake", "refresh_token": "refresh-fake", "scope": "gmail.send",
        }
        self._email = email
        self._falhar_troca = falhar_troca
        self.revogado_com = None

    def url_autorizacao(self, state: str) -> str:
        return f"https://accounts.google.com/o/oauth2/v2/auth?state={state}"

    def trocar_codigo(self, code: str) -> dict:
        if self._falhar_troca:
            raise ErroGoogleOAuth("O Google recusou o código de autorização (status 400).")
        return self._tokens

    def email_conectado(self, access_token: str) -> str:
        return self._email

    def revogar(self, refresh_token: str) -> bool:
        self.revogado_com = refresh_token
        return True


@pytest.fixture
def google_falso():
    falso = ClienteGoogleFalso()
    app.dependency_overrides[get_google_oauth_client] = lambda: falso
    yield falso
    app.dependency_overrides.pop(get_google_oauth_client, None)


def test_listar_exige_admin(client, vendedor_headers, admin_headers, google_falso):
    r = client.get("/caixas-envio", headers=vendedor_headers)
    assert r.status_code == 403

    r = client.get("/caixas-envio", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_conectar_sem_oauth_configurado_e_503(client, admin_headers):
    app.dependency_overrides[get_google_oauth_client] = lambda: ClienteGoogleFalso(configurado=False)
    try:
        r = client.get("/caixas-envio/conectar", headers=admin_headers)
    finally:
        app.dependency_overrides.pop(get_google_oauth_client, None)
    assert r.status_code == 503


def test_conectar_devolve_url_com_state_do_admin(client, admin_headers, google_falso):
    r = client.get("/caixas-envio/conectar", headers=admin_headers)
    assert r.status_code == 200
    url = r.json()["url_autorizacao"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert state  # é um JWT — o teste de callback confirma que decodifica para o admin certo


def test_conectar_exige_admin(client, vendedor_headers, google_falso):
    r = client.get("/caixas-envio/conectar", headers=vendedor_headers)
    assert r.status_code == 403


def test_callback_sem_code_redireciona_com_erro(client, google_falso):
    r = client.get("/caixas-envio/callback", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "erro=" in r.headers["location"]


def test_callback_state_invalido_redireciona_com_erro(client, google_falso):
    r = client.get(
        "/caixas-envio/callback", params={"code": "abc", "state": "nao-e-um-jwt"}, follow_redirects=False
    )
    assert "erro=" in r.headers["location"]


def test_callback_google_recusa_codigo_redireciona_com_erro(client, db, admin):
    app.dependency_overrides[get_google_oauth_client] = lambda: ClienteGoogleFalso(falhar_troca=True)
    try:
        state = criar_state_oauth(str(admin.id))
        r = client.get(
            "/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False
        )
    finally:
        app.dependency_overrides.pop(get_google_oauth_client, None)
    assert "erro=" in r.headers["location"]
    assert db.query(CaixaEnvio).count() == 0


def test_callback_sucesso_cria_caixa_sem_nunca_expor_o_token(client, db, admin, admin_headers, google_falso):
    state = criar_state_oauth(str(admin.id))
    r = client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "conectado=1" in r.headers["location"]

    caixa = db.query(CaixaEnvio).one()
    assert caixa.email == "caixa@prospeccao.exemplo.com.br"
    assert caixa.refresh_token_criptografado != "refresh-fake"  # está criptografado, não em texto puro
    assert caixa.conectada_por == admin.id

    listagem = client.get("/caixas-envio", headers=admin_headers)
    assert "refresh-fake" not in listagem.text
    assert "refresh_token" not in listagem.text


def test_callback_reconectar_mesma_caixa_atualiza_token(client, db, admin, google_falso):
    state = criar_state_oauth(str(admin.id))
    client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    anterior = db.query(CaixaEnvio).one().refresh_token_criptografado

    google_falso._tokens = {"access_token": "novo", "refresh_token": "outro-refresh", "scope": "gmail.send"}
    state2 = criar_state_oauth(str(admin.id))
    client.get("/caixas-envio/callback", params={"code": "def", "state": state2}, follow_redirects=False)

    assert db.query(CaixaEnvio).count() == 1  # upsert por e-mail, não duplica
    assert db.query(CaixaEnvio).one().refresh_token_criptografado != anterior


def test_ativar_desativar_exige_admin(client, db, admin, vendedor_headers, admin_headers, google_falso):
    state = criar_state_oauth(str(admin.id))
    client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    caixa_id = db.query(CaixaEnvio).one().id

    r = client.post(f"/caixas-envio/{caixa_id}/desativar", headers=vendedor_headers)
    assert r.status_code == 403

    r = client.post(f"/caixas-envio/{caixa_id}/desativar", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ativa"] is False

    r = client.post(f"/caixas-envio/{caixa_id}/ativar", headers=admin_headers)
    assert r.json()["ativa"] is True


def test_editar_limite_exige_admin(client, db, admin, vendedor_headers, admin_headers, google_falso):
    state = criar_state_oauth(str(admin.id))
    client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    caixa_id = db.query(CaixaEnvio).one().id

    r = client.post(
        f"/caixas-envio/{caixa_id}/limite", json={"limite_diario": 10}, headers=vendedor_headers
    )
    assert r.status_code == 403

    r = client.post(
        f"/caixas-envio/{caixa_id}/limite", json={"limite_diario": 10}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["limite_diario"] == 10


def test_editar_limite_zero_ou_negativo_e_422(client, db, admin, admin_headers, google_falso):
    state = criar_state_oauth(str(admin.id))
    client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    caixa_id = db.query(CaixaEnvio).one().id

    for valor in (0, -5):
        r = client.post(
            f"/caixas-envio/{caixa_id}/limite", json={"limite_diario": valor}, headers=admin_headers
        )
        assert r.status_code == 422


def test_editar_limite_caixa_inexistente_e_404(client, admin_headers):
    r = client.post(
        f"/caixas-envio/{uuid.uuid4()}/limite", json={"limite_diario": 10}, headers=admin_headers
    )
    assert r.status_code == 404


def test_remover_tenta_revogar_e_remove_mesmo_se_revogacao_falhar(client, db, admin, admin_headers):
    # `ClienteGoogleOAuth.revogar` real nunca levanta (engole httpx.HTTPError e devolve False) — o dublê
    # imita exatamente isso: devolve False em vez de confirmar a revogação.
    falso = ClienteGoogleFalso()
    falso.revogar = lambda token: False
    app.dependency_overrides[get_google_oauth_client] = lambda: falso
    try:
        state = criar_state_oauth(str(admin.id))
        client.get("/caixas-envio/callback", params={"code": "abc", "state": state}, follow_redirects=False)
        caixa_id = db.query(CaixaEnvio).one().id

        r = client.delete(f"/caixas-envio/{caixa_id}", headers=admin_headers)
        assert r.status_code == 204
        assert db.query(CaixaEnvio).count() == 0
    finally:
        app.dependency_overrides.pop(get_google_oauth_client, None)
