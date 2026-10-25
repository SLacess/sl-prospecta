"""Tarefa 5: Ficha do Prospect, mini-relatório e prints (tudo com login, nada de endereço s3:// na saída)."""

import uuid

import pytest

from app.artefatos import chave_relatorio, get_armazenamento
from app.main import app
from app.models import Auditoria, Dossie, Empresa, EstadoProspect, Evento


class ArmazenamentoFalso:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}

    def ler(self, chave):
        return self.arquivos.get(chave)

    def existe(self, chave):
        return chave in self.arquivos


@pytest.fixture
def armazenamento():
    falso = ArmazenamentoFalso()
    app.dependency_overrides[get_armazenamento] = lambda: falso
    return falso


PRINT_HOME = "s3://artefatos/auditorias/x/y/01-desktop.png"
PRINT_CONTATO = "s3://artefatos/auditorias/x/y/02-desktop.png"
ANALISE = {
    "nota_geral": 53,
    "top3_para_leigos": [
        {
            "titulo": "Imagens sem descrição",
            "impacto_humano": "...",
            "quem_e_afetado": ["pessoas cegas"],
            "criterio_wcag": "1.1.1",
            "pagina": "/",
            "pagina_url": "https://h.com.br/",
            "problema": "image-alt",
            "evidencia": {"print": PRINT_HOME, "trecho_html": "<img>"},
        },
        {
            "titulo": "Formulário sem rótulos",
            "impacto_humano": "...",
            "quem_e_afetado": ["pessoas cegas"],
            "criterio_wcag": "1.3.1",
            "pagina": "/contato",
            "pagina_url": "https://h.com.br/contato",
            "problema": "label",
            "evidencia": {"print": None, "trecho_html": None},
        },
    ],
    "plugin_resolve_parcialmente": [],
    "exige_ajuste_no_codigo": ["imagens sem texto alternativo"],
    "indicios_visuais": [],
    "observacao_honestidade": "Testes automáticos encontram só parte das barreiras.",
}
PAGINAS = [
    {
        "url": "https://h.com.br/",
        "status": "ok",
        "plugins": [],
        "axe": {
            "violacoes": [{"regra": "image-alt", "caixa": {"x": 683, "y": 384, "largura": 137, "altura": 77}}]
        },
        "teclado": {},
        "responsivo_320": {},
    }
]


def _empresa_completa(db):
    empresa = Empresa(
        nome="Hospital H",
        dominio="h.com.br",
        fonte="manual",
        estado=EstadoProspect.qualificando,
        setor="saude",
        cidade="Sorocaba",
        uf="SP",
    )
    db.add(empresa)
    db.flush()
    db.add(
        Dossie(
            empresa_id=empresa.id,
            versao=1,
            resumo="L1\nL2\nL3\nL4\nL5",
            dados_json={
                "descricao": "Hospital geral.",
                "missao": None,
                "produtos_servicos": ["pronto-socorro"],
                "publicos_atendidos": ["pacientes"],
                "localizacao": {"cidade": "Sorocaba", "uf": "SP", "url": "https://h.com.br/"},
                "porte_indicios": None,
                "lacunas": ["sem página de ESG"],
                "paginas_lidas": ["https://h.com.br/"],
                "tecnologias_site": ["WordPress"],
                "raciocinio_resumido": "ok",
                "mencoes_inclusao": [
                    {"tema": "pcd", "trecho": "Programa de inclusão", "url": "https://h.com.br/"}
                ],
                "sinais": [{"tipo": "outro", "descricao": "Programa", "url": "https://h.com.br/"}],
            },
        )
    )
    auditoria = Auditoria(
        empresa_id=empresa.id,
        nota=53,
        achados_json=ANALISE,
        paginas_json=PAGINAS,
        totais_json={"critico": 2},
        artefatos_urls=[PRINT_HOME, "s3://artefatos/x/320.png"],
    )
    db.add(auditoria)
    db.add(
        Evento(
            empresa_id=empresa.id,
            tipo="relatorio_pronto",
            origem="sistema",
            dados_json={"mensagem": "Mini-relatório pronto."},
        )
    )
    db.commit()
    return empresa, auditoria


def test_ficha_traz_dossie_auditoria_evidencias_e_linha_do_tempo(client, db, vendedor_headers, armazenamento):
    empresa, auditoria = _empresa_completa(db)
    armazenamento.arquivos[chave_relatorio(empresa.id, auditoria.id, "pdf")] = b"%PDF"

    r = client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers)
    assert r.status_code == 200
    f = r.json()
    assert (f["empresa"]["setor"], f["empresa"]["cidade"], f["empresa"]["uf"]) == ("saude", "Sorocaba", "SP")
    assert f["dossie"]["resumo"] == ["L1", "L2", "L3", "L4", "L5"]
    assert f["dossie"]["mencoes_inclusao"][0]["trecho"] == "Programa de inclusão"
    assert f["dossie"]["lacunas"] == ["sem página de ESG"]
    assert f["auditoria"]["nota"] == 53
    assert f["relatorio_disponivel"] is True
    assert f["eventos"][-1]["tipo"] == "relatorio_pronto"

    home, contato = f["evidencias"]
    assert home["print_indice"] == 0
    assert home["caixa"] == {"left": 50.0, "top": 50.0, "width": 10.03, "height": 10.03}
    assert "destacado" in home["alt"]
    assert contato["print_indice"] is None and contato["caixa"] is None
    assert "s3://" not in r.text


def test_relatorio_indisponivel_antes_de_gerar(client, db, vendedor_headers, armazenamento):
    empresa, _ = _empresa_completa(db)
    assert (
        client.get(f"/empresas/{empresa.id}/ficha", headers=vendedor_headers).json()["relatorio_disponivel"]
        is False
    )
    r = client.get(f"/empresas/{empresa.id}/relatorio.pdf", headers=vendedor_headers)
    assert r.status_code == 404
    assert "ainda não foi gerado" in r.json()["detail"]


def test_baixa_o_pdf_e_a_versao_web(client, db, leitura_headers, armazenamento):
    empresa, auditoria = _empresa_completa(db)
    armazenamento.arquivos[chave_relatorio(empresa.id, auditoria.id, "pdf")] = b"%PDF-1.7 teste"
    armazenamento.arquivos[chave_relatorio(empresa.id, auditoria.id, "html")] = b"<html lang='pt-BR'>ok</html>"

    pdf = client.get(f"/empresas/{empresa.id}/relatorio.pdf", headers=leitura_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert 'filename="diagnostico-acessibilidade-h-com-br.pdf"' in pdf.headers["content-disposition"]
    assert pdf.content == b"%PDF-1.7 teste"

    web = client.get(f"/empresas/{empresa.id}/relatorio", headers=leitura_headers)
    assert web.headers["content-type"].startswith("text/html")
    assert "pt-BR" in web.text


def test_print_so_pelo_indice_e_com_login(client, db, vendedor_headers, armazenamento):
    empresa, _ = _empresa_completa(db)
    armazenamento.arquivos["auditorias/x/y/01-desktop.png"] = b"\x89PNG"
    r = client.get(f"/empresas/{empresa.id}/prints/0", headers=vendedor_headers)
    assert (r.status_code, r.headers["content-type"], r.content) == (200, "image/png", b"\x89PNG")
    assert client.get(f"/empresas/{empresa.id}/prints/1", headers=vendedor_headers).status_code == 404
    assert client.get(f"/empresas/{empresa.id}/prints/9", headers=vendedor_headers).status_code == 404
    assert client.get(f"/empresas/{empresa.id}/prints/0").status_code == 401


@pytest.mark.parametrize("rota", ["ficha", "relatorio.pdf", "relatorio", "prints/0"])
def test_rotas_exigem_login(client, db, armazenamento, rota):
    empresa, _ = _empresa_completa(db)
    assert client.get(f"/empresas/{empresa.id}/{rota}").status_code == 401


def test_empresa_inexistente_404(client, vendedor_headers, armazenamento):
    assert client.get(f"/empresas/{uuid.uuid4()}/ficha", headers=vendedor_headers).status_code == 404
