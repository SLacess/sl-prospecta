"""Fase 2, Tarefa 2: decisores na Ficha (e-mail mascarado para o perfil leitura) e disjuntor do Apollo."""

from app.config import get_settings
from app.models import AcaoAgente, Contato, Empresa, EstadoProspect


def _empresa_com_decisores(db):
    empresa = Empresa(nome="Hospital D", dominio="d.com.br", fonte="manual",
                      estado=EstadoProspect.preparando_abordagem)
    db.add(empresa)
    db.flush()
    db.add_all([
        Contato(empresa_id=empresa.id, nome="Ana Souza", cargo="CTO", area="TI", email="ana@d.com.br",
                email_status="valido", linkedin_url="http://www.linkedin.com/in/ana", fonte="apollo"),
        Contato(empresa_id=empresa.id, nome="Bruno Lopes", cargo="CMO", area="Marketing", email=None,
                email_status="sem_email", fonte="web+apollo", fonte_url="https://d.com.br/diretoria"),
        Contato(empresa_id=empresa.id, nome="Saiu", cargo="RH", area="RH", email="saiu@d.com.br",
                email_status="valido", fonte="apollo", opt_out=True),
    ])
    db.commit()
    return empresa


def test_ficha_lista_os_decisores_com_o_status_do_email_em_texto(client, db, vendedor_headers):
    empresa = _empresa_com_decisores(db)
    decisores = client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers).json()["decisores"]
    assert [d["nome"] for d in decisores] == ["Ana Souza", "Bruno Lopes"]  # opt-out não aparece
    ana, bruno = decisores
    assert (ana["email"], ana["rotulo_email"], ana["area"]) == ("ana@d.com.br", "e-mail verificado", "TI")
    assert (bruno["email"], bruno["rotulo_email"], bruno["fonte_url"]) == (None, "sem e-mail",
                                                                          "https://d.com.br/diretoria")


def test_perfil_leitura_ve_o_email_mascarado(client, db, leitura_headers):
    empresa = _empresa_com_decisores(db)
    decisores = client.get(f"/empresas/{empresa.id}/ficha", headers=leitura_headers).json()["decisores"]
    assert decisores[0]["email"] == "a***@d.com.br"


def test_disjuntor_do_apollo_soma_os_creditos_do_dia(client, db, vendedor_headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "apollo_daily_credit_cap", 5)
    db.add_all([
        AcaoAgente(agente="mapeador.apollo", entrada_hash="x", saida_json={}, creditos=3),
        AcaoAgente(agente="mapeador", entrada_hash="y", saida_json={}, creditos=0),
    ])
    db.commit()
    apollo = client.get("/governanca/disjuntores", headers=vendedor_headers).json()["apollo"]
    assert apollo == {"creditos_hoje": 3, "teto": 5, "atingido": False,
                      "mensagem": "Créditos do Apollo hoje: 3 de 5."}

    db.add(AcaoAgente(agente="mapeador.apollo", entrada_hash="z", saida_json={}, creditos=2))
    db.commit()
    apollo = client.get("/governanca/disjuntores", headers=vendedor_headers).json()["apollo"]
    assert apollo["atingido"] is True
    assert "recomeça amanhã" in apollo["mensagem"]
