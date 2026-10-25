"""Revisão humana dos achados e placar do critério da Fase 1 (CONSTITUICAO §19, ADR 0007)."""

import pytest

from app.models import Auditoria, Empresa, EstadoProspect, Evento, Papel, Usuario
from app.security import hash_password


@pytest.fixture
def admin_headers(client, admin):
    r = client.post("/auth/login", data={"username": "admin@exemplo.com", "password": "senha-muito-forte"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _achado(problema, titulo):
    return {
        "titulo": titulo,
        "impacto_humano": "...",
        "quem_e_afetado": [],
        "criterio_wcag": "1.1.1",
        "pagina": "/",
        "pagina_url": "https://x.com.br/",
        "problema": problema,
        "evidencia": {},
    }


ANALISE = {
    "top3_para_leigos": [
        _achado("image-alt", "Imagens sem descrição"),
        _achado("label", "Campos sem rótulo"),
        _achado("teclado:armadilha_de_foco", "Foco preso"),
    ]
}
PAGINAS = [
    {
        "url": "https://x.com.br/",
        "status": "ok",
        "axe": {
            "violacoes": [
                {"regra": "image-alt", "descricao": "Imagens precisam de alt"},
                {"regra": "label", "descricao": "Campos precisam de rótulo"},
                {"regra": "color-contrast", "descricao": "Contraste"},
            ]
        },
        "teclado": {"armadilha_de_foco": {"elementos": ["a"]}, "link_pular_conteudo": True},
        "responsivo_320": {},
    }
]


def _auditoria(db, nome="x.com.br", setor="saude", nota=50):
    empresa = Empresa(
        nome=nome, dominio=nome, fonte="manual", estado=EstadoProspect.qualificando, setor=setor
    )
    db.add(empresa)
    db.flush()
    auditoria = Auditoria(
        empresa_id=empresa.id,
        nota=nota,
        achados_json=ANALISE,
        paginas_json=PAGINAS,
        totais_json={},
        artefatos_urls=[],
    )
    db.add(auditoria)
    db.commit()
    return auditoria


def _revisao(vereditos=("correto", "correto", "correto"), tecnicos=(), honestos=True):
    chaves = ["image-alt", "label", "teclado:armadilha_de_foco"]
    return {
        "achados": [
            {"chave": c, "veredito": v, "motivo": None if v == "correto" else "ver WAVE"}
            for c, v in zip(chaves, vereditos, strict=True)
        ],
        "tecnicos": [
            {"chave": c, "veredito": v, "motivo": None if v == "correto" else "falso positivo"}
            for c, v in tecnicos
        ],
        "textos_honestos": honestos,
    }


def test_itens_revisaveis_da_auditoria(client, db, vendedor_headers):
    a = _auditoria(db)
    r = client.get(f"/auditorias/{a.id}/revisao", headers=vendedor_headers).json()
    assert [i["chave"] for i in r["achados"]] == ["image-alt", "label", "teclado:armadilha_de_foco"]
    assert r["achados"][0]["rotulo"] == "Imagens sem descrição"
    assert [i["chave"] for i in r["tecnicos"]] == [
        "color-contrast",
        "image-alt",
        "label",
        "teclado:armadilha_de_foco",
    ]
    assert r["completa"] is False and r["textos_honestos"] is None


def test_admin_salva_e_corrige_a_revisao(client, db, admin_headers):
    a = _auditoria(db)
    r = client.put(
        f"/auditorias/{a.id}/revisao", json=_revisao(("correto", "parcial", "correto")), headers=admin_headers
    )
    assert r.status_code == 200
    assert r.json()["completa"] is True
    assert r.json()["achados"][1] == {
        "chave": "label",
        "rotulo": "Campos sem rótulo",
        "pagina": "/",
        "veredito": "parcial",
        "motivo": "ver WAVE",
    }
    # Salvar de novo atualiza, sem duplicar
    r2 = client.put(f"/auditorias/{a.id}/revisao", json=_revisao(), headers=admin_headers)
    assert r2.json()["achados"][1]["veredito"] == "correto"
    assert db.query(Evento).filter(Evento.tipo == "revisao_salva").count() == 2


def test_motivo_obrigatorio_quando_nao_esta_correto(client, db, admin_headers):
    a = _auditoria(db)
    corpo = _revisao(("incorreto", "correto", "correto"))
    corpo["achados"][0]["motivo"] = "  "
    r = client.put(f"/auditorias/{a.id}/revisao", json=corpo, headers=admin_headers)
    assert r.status_code == 422
    assert "motivo" in r.json()["detail"]


def test_precisa_revisar_os_3_achados(client, db, admin_headers):
    a = _auditoria(db)
    corpo = _revisao()
    corpo["achados"] = corpo["achados"][:2]
    assert client.put(f"/auditorias/{a.id}/revisao", json=corpo, headers=admin_headers).status_code == 422


def test_problema_tecnico_inexistente_e_recusado(client, db, admin_headers):
    a = _auditoria(db)
    r = client.put(
        f"/auditorias/{a.id}/revisao",
        json=_revisao(tecnicos=[("inventado", "correto")]),
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_so_admin_revisa(client, db, vendedor_headers):
    a = _auditoria(db)
    assert (
        client.put(f"/auditorias/{a.id}/revisao", json=_revisao(), headers=vendedor_headers).status_code
        == 403
    )


def test_auditoria_sem_analise_nao_e_revisada(client, db, admin_headers):
    empresa = Empresa(nome="y.com.br", dominio="y.com.br", fonte="manual", estado=EstadoProspect.auditando)
    db.add(empresa)
    db.flush()
    a = Auditoria(empresa_id=empresa.id, achados_json=[], paginas_json=[], totais_json={}, artefatos_urls=[])
    db.add(a)
    db.commit()
    assert client.get(f"/auditorias/{a.id}/revisao", headers=admin_headers).status_code == 409


def test_placar_conta_parcial_como_meio_e_lista_pendencias(client, db, admin_headers, vendedor_headers):
    a1 = _auditoria(db, "a.com.br", "saude")
    a2 = _auditoria(db, "b.com.br", "educacao")
    _auditoria(db, "c.com.br", "saude")  # analisada, ainda não revisada
    client.put(
        f"/auditorias/{a1.id}/revisao",
        json=_revisao(("correto", "parcial", "correto")),
        headers=admin_headers,
    )
    client.put(
        f"/auditorias/{a2.id}/revisao",
        json=_revisao(("correto", "correto", "incorreto"), tecnicos=[("color-contrast", "correto")]),
        headers=admin_headers,
    )

    p = client.get("/revisao/fase1", headers=vendedor_headers).json()
    assert p["auditorias_revisadas"] == 2
    assert p["setores"] == 2
    # (1 + 0,5 + 1) + (1 + 1 + 0 + 1) = 5,5 de 7
    assert p["percentual_correto"] == 78.6
    assert p["atingido"] is False
    assert "faltam 18 auditoria(s) revisada(s)" in p["pendencias"]
    assert "faltam 2 setor(es) diferente(s)" in p["pendencias"]
    assert "acertos em 78.6%, abaixo de 90%" in p["pendencias"]
    assert [(linha["nome"], linha["revisada"]) for linha in p["lista"]] == [
        ("a.com.br", True),
        ("b.com.br", True),
        ("c.com.br", False),
    ]


def test_placar_atinge_o_criterio(client, db, admin_headers):
    for i in range(20):
        a = _auditoria(db, f"s{i:02d}.com.br", ["saude", "educacao", "financeiro", "ecommerce"][i % 4])
        vereditos = ("correto", "correto", "parcial") if i == 0 else ("correto", "correto", "correto")
        client.put(f"/auditorias/{a.id}/revisao", json=_revisao(vereditos), headers=admin_headers)
    p = client.get("/revisao/fase1", headers=admin_headers).json()
    assert (p["auditorias_revisadas"], p["setores"], p["percentual_correto"]) == (20, 4, 99.2)
    assert p["atingido"] is True and p["pendencias"] == []


def test_promessa_de_conformidade_impede_o_criterio(client, db, admin_headers):
    for i in range(20):
        a = _auditoria(db, f"p{i:02d}.com.br", ["saude", "educacao", "financeiro", "ecommerce"][i % 4])
        client.put(f"/auditorias/{a.id}/revisao", json=_revisao(honestos=i != 5), headers=admin_headers)
    p = client.get("/revisao/fase1", headers=admin_headers).json()
    assert p["promessas_encontradas"] == 1
    assert p["atingido"] is False


def test_outro_admin_tambem_pode_revisar(client, db):
    db.add(
        Usuario(
            nome="Outro",
            email="outro@exemplo.com",
            senha_hash=hash_password("senha-muito-forte"),
            papel=Papel.admin,
        )
    )
    db.commit()
    a = _auditoria(db)
    token = client.post(
        "/auth/login", data={"username": "outro@exemplo.com", "password": "senha-muito-forte"}
    )
    r = client.put(
        f"/auditorias/{a.id}/revisao",
        json=_revisao(),
        headers={"Authorization": f"Bearer {token.json()['access_token']}"},
    )
    assert r.status_code == 200
