"""Fase 2, Tarefa 3: upload de planilha (leitura, mapeamento, deduplicação, confirmação e progresso)."""

import io

import pytest

from app.models import Contato, Empresa, EstadoProspect, Evento, Lote
from app.planilha import (
    MAX_LINHAS,
    Planilha,
    PlanilhaInvalida,
    amostra_para_ia,
    cnpj_valido,
    ler_planilha,
    mapear_por_regras,
)

CNPJ_OK = "11222333000181"  # dígitos verificadores corretos
CSV = (
    "Razão Social;Site;CNPJ;Cidade;UF;Contato;Cargo;E-mail\n"
    "Hospital A;https://www.hospital-a.com.br/contato;11.222.333/0001-81;Sorocaba;SP;Ana;CTO;ana@hospital-a.com.br\n"
    "Hospital A (filial);hospital-a.com.br;;Itu;SP;;;\n"
    "Faculdade B;faculdade-b.edu.br;12.345.678/0001-00;Campinas;XX;;;\n"
    "Clínica C;;;;;Bruno;Diretor de Marketing;bruno@gmail.com\n"
    ";;;;;;;\n"
    ";site ruim;;;;;;\n"
    "Já Existe;existente.com.br;;;;;;\n"
)


def _xlsx(linhas: list[list]) -> bytes:
    from openpyxl import Workbook

    livro = Workbook()
    aba = livro.active
    for linha in linhas:
        aba.append(linha)
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


# --- Leitura -------------------------------------------------------------------


def test_le_csv_com_ponto_e_virgula_e_latin1():
    p = ler_planilha("lista.csv", CSV.encode("cp1252"))
    assert p.cabecalhos[0] == "Razão Social"
    assert p.total == 6  # a linha em branco não conta, mas fica para a numeração bater com o arquivo
    assert p.linhas[0][1] == "https://www.hospital-a.com.br/contato"


def test_le_csv_utf8_com_bom_e_virgula():
    p = ler_planilha("lista.csv", "﻿Empresa,Site\nX,x.com.br\n".encode())
    assert p.cabecalhos == ["Empresa", "Site"] and p.linhas == [["X", "x.com.br"]]


def test_le_xlsx_e_cnpj_numerico_nao_vira_notacao_cientifica():
    p = ler_planilha("lista.xlsx", _xlsx([["Empresa", "CNPJ"], ["X", 11222333000181]]))
    assert p.linhas == [["X", "11222333000181"]]


@pytest.mark.parametrize(
    "nome, dados, mensagem",
    [
        ("lista.xlsm", b"PK...", "Envie uma planilha .xlsx ou .csv."),
        ("lista.xlsx", b"nao e zip", "não é um .xlsx válido"),
        ("lista.csv", b"", "vazia"),
        ("lista.csv", b"Empresa;Site\n", "só tem o cabeçalho"),
        ("lista.csv", b"x" * (5 * 1024 * 1024 + 1), "passa de 5 MB"),
    ],
)
def test_arquivos_recusados(nome, dados, mensagem):
    with pytest.raises(PlanilhaInvalida, match=mensagem):
        ler_planilha(nome, dados)


def test_limite_de_linhas():
    corpo = "Empresa\n" + "\n".join(f"E{i}" for i in range(MAX_LINHAS + 1))
    with pytest.raises(PlanilhaInvalida, match="limite é 1000"):
        ler_planilha("lista.csv", corpo.encode())


def test_xlsx_com_macro_e_recusado():
    import zipfile

    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("xl/vbaProject.bin", b"x")
    with pytest.raises(PlanilhaInvalida, match="macros"):
        ler_planilha("lista.xlsx", saida.getvalue())


# --- Mapeamento e linhas -----------------------------------------------------


def test_mapeamento_por_regras_reconhece_os_cabecalhos():
    mapa = mapear_por_regras(ler_planilha("lista.csv", CSV.encode()))
    assert mapa == {
        "empresa": 0,
        "site": 1,
        "cnpj": 2,
        "cidade": 3,
        "uf": 4,
        "contato_nome": 5,
        "contato_cargo": 6,
        "contato_email": 7,
    }


def test_coluna_de_site_sem_cabecalho_conhecido_e_achada_pelo_conteudo():
    p = Planilha(cabecalhos=["Nome", "Endereço"], linhas=[["A", "a.com.br"], ["B", "www.b.org"]])
    assert mapear_por_regras(p)["site"] == 1 and mapear_por_regras(p)["empresa"] == 0


@pytest.mark.parametrize("cnpj, ok", [(CNPJ_OK, True), ("11222333000180", False), ("11111111111111", False)])
def test_cnpj(cnpj, ok):
    assert cnpj_valido(cnpj) is ok


def test_amostra_para_ia_mascara_emails_e_limita_exemplos():
    p = ler_planilha("lista.csv", CSV.encode())
    amostra = amostra_para_ia(p.cabecalhos, p.linhas)
    assert amostra[7]["exemplos"][0] == "a***@hospital-a.com.br"
    assert all(len(c["exemplos"]) <= 3 for c in amostra)


# --- Fluxo pela API ----------------------------------------------------------


def _enviar(client, headers, conteudo=CSV, nome="lista.csv"):
    dados = conteudo.encode() if isinstance(conteudo, str) else conteudo
    return client.post("/lotes", files={"arquivo": (nome, dados, "text/csv")}, headers=headers)


def test_previa_classifica_cada_linha_e_estima_o_custo(client, db, vendedor_headers, fila):
    db.add(Empresa(nome="Já Existe", dominio="existente.com.br", fonte="manual", estado=EstadoProspect.novo))
    db.commit()
    r = _enviar(client, vendedor_headers)
    assert r.status_code == 201, r.text
    lote = r.json()
    assert lote["status"] == "aguardando_confirmacao" and lote["mapeamento_origem"] == "regras"
    assert fila.mapeamentos == []  # empresa e site achados pelas regras: sem IA
    assert lote["resumo"] == {
        "total": 6,
        "novas": 3,
        "ja_cadastradas": 1,
        "repetidas": 1,
        "invalidas": 1,
        "com_avisos": 1,
    }
    situacoes = {p["numero"]: (p["situacao"], p["motivo"]) for p in lote["previa"]}
    assert situacoes[2] == ("nova", None)
    assert situacoes[3] == ("repetida", "repete a linha 2")
    assert situacoes[4][0] == "nova"  # CNPJ e UF errados viram aviso, não descartam a empresa
    assert situacoes[5][0] == "nova"  # só nome: o Pesquisador acha o site
    assert 6 not in situacoes  # linha em branco no meio da planilha
    assert situacoes[7] == ("invalida", "sem nome da empresa nem site legível")
    assert situacoes[8] == ("ja_cadastrada", "já cadastrada como Já Existe")
    faculdade = next(p for p in lote["previa"] if p["numero"] == 4)
    assert any("CNPJ" in a for a in faculdade["avisos"]) and any("UF" in a for a in faculdade["avisos"])
    assert "3 empresa(s) nova(s)" in lote["estimativa"]["texto"]
    assert lote["estimativa"]["creditos_apollo"] == 12


def test_sem_coluna_de_empresa_ou_site_pede_a_ia(client, vendedor_headers, fila):
    r = _enviar(client, vendedor_headers, "Coluna X;Coluna Y\nfoo;bar\n")
    assert r.json()["status"] == "mapeando"
    _, colunas = fila.mapeamentos[0]
    assert [c["cabecalho"] for c in colunas] == ["Coluna X", "Coluna Y"]


def test_sem_fila_a_previa_segue_com_as_regras_e_avisa(client, vendedor_headers, fila):
    fila.indisponivel = True
    lote = _enviar(client, vendedor_headers, "Coluna X;Coluna Y\nfoo;bar\n").json()
    assert lote["status"] == "aguardando_confirmacao"
    assert "Confira as colunas" in lote["aviso_mapeamento"]


def test_ajuste_de_colunas_pelo_vendedor(client, vendedor_headers, fila):
    lote = _enviar(client, vendedor_headers, "Coluna X;Coluna Y\nHospital Z;z.com.br\n").json()
    mapa = {
        c: None
        for c in ("empresa", "site", "cnpj", "cidade", "uf", "contato_nome", "contato_cargo", "contato_email")
    }
    r = client.put(
        f"/lotes/{lote['id']}/mapeamento",
        json={"mapeamento": {**mapa, "empresa": 0, "site": 1}},
        headers=vendedor_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["mapeamento_origem"] == "humano"
    assert r.json()["previa"][0]["site"] == "z.com.br"

    repetida = client.put(
        f"/lotes/{lote['id']}/mapeamento",
        json={"mapeamento": {**mapa, "empresa": 0, "site": 0}},
        headers=vendedor_headers,
    )
    assert repetida.status_code == 422 and "dois campos" in repetida.json()["detail"]


def test_confirmar_cadastra_enfileira_e_apaga_as_linhas(client, db, vendedor_headers, fila):
    existente = Empresa(
        nome="Já Existe", dominio="existente.com.br", fonte="manual", estado=EstadoProspect.novo
    )
    db.add(existente)
    db.commit()
    lote = _enviar(client, vendedor_headers).json()
    r = client.post(f"/lotes/{lote['id']}/confirmar", headers=vendedor_headers)
    assert r.status_code == 200, r.text
    detalhe = r.json()
    assert detalhe["status"] == "processando"
    assert detalhe["progresso"]["total"] == 3 and detalhe["progresso"]["finalizadas"] == 0
    assert {e["nome"] for e in detalhe["empresas"]} == {"Hospital A", "Faculdade B", "Clínica C"}
    assert len(fila.enviados) == 3
    assert {i["linha"] for i in detalhe["linhas_ignoradas"]} == {3, 7, 8}

    db.expire_all()
    salvo = db.query(Lote).one()
    assert salvo.linhas_json is None  # coleta mínima
    hospital = db.query(Empresa).filter(Empresa.dominio == "hospital-a.com.br").one()
    assert (hospital.cnpj, hospital.cidade, hospital.uf, hospital.fonte) == (
        CNPJ_OK,
        "Sorocaba",
        "SP",
        "lote",
    )
    faculdade = db.query(Empresa).filter(Empresa.dominio == "faculdade-b.edu.br").one()
    assert faculdade.cnpj is None and faculdade.uf is None
    clinica = db.query(Empresa).filter(Empresa.nome == "Clínica C").one()
    assert clinica.dominio is None

    ana = db.query(Contato).filter(Contato.empresa_id == hospital.id).one()
    assert (ana.nome, ana.area, ana.email_status, ana.fonte) == ("Ana", "TI", "nao_verificado", "planilha")
    bruno = db.query(Contato).filter(Contato.empresa_id == clinica.id).one()
    assert (bruno.email, bruno.email_status, bruno.area) == (
        None,
        "sem_email",
        "Marketing",
    )  # webmail descartado

    eventos_existente = db.query(Evento).filter(Evento.empresa_id == existente.id).all()
    assert [e.tipo for e in eventos_existente] == ["entrada_duplicada"]
    assert "linha 8" in eventos_existente[0].dados_json["mensagem"]


def test_lote_confirmado_nao_confirma_de_novo_nem_cancela(client, vendedor_headers, fila):
    lote = _enviar(client, vendedor_headers).json()
    client.post(f"/lotes/{lote['id']}/confirmar", headers=vendedor_headers)
    assert client.post(f"/lotes/{lote['id']}/confirmar", headers=vendedor_headers).status_code == 409
    assert client.post(f"/lotes/{lote['id']}/cancelar", headers=vendedor_headers).status_code == 409


def test_cancelar_apaga_as_linhas(client, db, vendedor_headers, fila):
    lote = _enviar(client, vendedor_headers).json()
    r = client.post(f"/lotes/{lote['id']}/cancelar", headers=vendedor_headers)
    assert r.json()["status"] == "cancelado"
    db.expire_all()
    assert db.query(Lote).one().linhas_json is None
    assert db.query(Empresa).count() == 0


def test_progresso_conta_etapas_e_problemas(client, db, vendedor_headers, fila):
    lote = _enviar(client, vendedor_headers).json()
    client.post(f"/lotes/{lote['id']}/confirmar", headers=vendedor_headers)
    hospital = db.query(Empresa).filter(Empresa.dominio == "hospital-a.com.br").one()
    faculdade = db.query(Empresa).filter(Empresa.dominio == "faculdade-b.edu.br").one()
    hospital.estado = EstadoProspect.preparando_abordagem
    faculdade.estado = EstadoProspect.pesquisando
    from datetime import UTC, datetime, timedelta

    db.add(
        Evento(
            empresa_id=faculdade.id,
            tipo="site_indisponivel",
            origem="sistema",
            dados_json={"mensagem": "x"},
            ocorrido_em=datetime.now(UTC) + timedelta(seconds=5),
        )
    )
    db.commit()
    detalhe = client.get(f"/lotes/{lote['id']}", headers=vendedor_headers).json()
    etapas = {e["chave"]: e["quantidade"] for e in detalhe["progresso"]["etapas"]}
    # Sem "Já Existe" no banco, ela também entrou como nova: Clínica C e Já Existe seguem na fila
    assert etapas["com_decisores"] == 1 and etapas["com_problema"] == 1 and etapas["na_fila"] == 2
    assert detalhe["progresso"]["finalizadas"] == 2
    faculdade_out = next(e for e in detalhe["empresas"] if e["dominio"] == "faculdade-b.edu.br")
    assert faculdade_out["problema"] == "site não pôde ser lido"


def test_lote_conclui_quando_ninguem_esta_em_andamento(client, db, vendedor_headers, fila):
    lote = _enviar(client, vendedor_headers, "Empresa;Site\nX;x.com.br\n").json()
    client.post(f"/lotes/{lote['id']}/confirmar", headers=vendedor_headers)
    db.query(Empresa).update({Empresa.estado: EstadoProspect.qualificando})
    db.commit()
    listado = client.get("/lotes", headers=vendedor_headers).json()[0]
    assert (listado["status"], listado["rotulo_status"]) == ("concluido", "Concluído")


def test_leitura_nao_envia_nem_confirma(client, leitura_headers, vendedor_headers, fila):
    assert _enviar(client, leitura_headers).status_code == 403
    lote = _enviar(client, vendedor_headers).json()
    assert client.post(f"/lotes/{lote['id']}/confirmar", headers=leitura_headers).status_code == 403
    assert client.get(f"/lotes/{lote['id']}", headers=leitura_headers).status_code == 200


def test_arquivo_invalido_responde_com_mensagem(client, vendedor_headers, fila):
    r = _enviar(client, vendedor_headers, b"PK", nome="lista.xls")
    assert r.status_code == 422 and r.json()["detail"] == "Envie uma planilha .xlsx ou .csv."
