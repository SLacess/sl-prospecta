from app.models import EstadoProspect


def _login(client, email="admin@exemplo.com", senha="senha-muito-forte"):
    return client.post("/auth/login", data={"username": email, "password": senha})


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["componentes"]["database"] == "ok"


def test_login_e_me(client, admin):
    r = _login(client)
    assert r.status_code == 200
    token = r.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["papel"] == "admin"


def test_login_senha_errada(client, admin):
    assert _login(client, senha="errada").status_code == 401


def test_me_sem_token(client):
    assert client.get("/auth/me").status_code == 401


def test_admin_cria_vendedor_e_vendedor_nao_cria(client, admin):
    token = _login(client).json()["access_token"]
    r = client.post(
        "/auth/usuarios",
        json={"nome": "José", "email": "jose@exemplo.com", "senha": "outra-senha-forte", "papel": "vendedor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201

    token_vendedor = _login(client, "jose@exemplo.com", "outra-senha-forte").json()["access_token"]
    r2 = client.post(
        "/auth/usuarios",
        json={"nome": "X", "email": "x@exemplo.com", "senha": "senha-qualquer-1", "papel": "admin"},
        headers={"Authorization": f"Bearer {token_vendedor}"},
    )
    assert r2.status_code == 403


def test_maquina_de_estados_completa():
    """Garante que os estados batem com a CONSTITUICAO §7.1."""
    assert len(EstadoProspect) == 16
    assert EstadoProspect.novo.value == "NOVO"
    assert EstadoProspect.ganho.value == "GANHO"
