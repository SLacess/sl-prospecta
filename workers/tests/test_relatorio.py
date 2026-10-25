"""Mini-relatório (Tarefa 5, CONSTITUICAO §8.3): conteúdo, honestidade, PDF acessível e orquestração."""

import asyncio
import io
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from slp_workers.audit.artefatos import ArmazenamentoMemoria
from slp_workers.audit.regras import Problema
from slp_workers.db import auditorias, empresas, eventos
from slp_workers.documents.relatorio import (
    DadosRelatorio,
    RelatorioDesonesto,
    comparacao_setor,
    escolher_acoes,
    gerar_html,
    montar_contexto,
)
from slp_workers.orchestrator.relatorio import chave_relatorio, gerar_com_evento, gerar_e_salvar
from tests.conftest import inserir_empresa

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\xdac\xfc\xff\x9f\xa1\x1e\x00\x07\x82\x02\x7f=\xc8H\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)
HOME = "https://h.com.br/"
PRINT = "s3://teste/auditorias/h/01-desktop.png"


def _pr(chave, gravidade="critico"):
    return Problema(chave=chave, gravidade=gravidade, paginas=(HOME,), ocorrencias=1, descricao="")


def _achado(
    titulo="Imagens da página inicial não têm descrição", problema="image-alt", grupos=("pessoas cegas",)
):
    return {
        "titulo": titulo,
        "impacto_humano": "Quem usa leitor de tela não sabe o que as imagens mostram.",
        "quem_e_afetado": list(grupos),
        "criterio_wcag": "1.1.1",
        "pagina": "/",
        "pagina_url": HOME,
        "problema": problema,
        "evidencia": {"print": PRINT, "trecho_html": "<img>"},
    }


ANALISE = {
    "nota_geral": 53,
    "paginas_auditadas": 3,
    "totais": {"critico": 2, "grave": 4, "moderado": 1, "leve": 0},
    "top3_para_leigos": [
        _achado(),
        _achado("Links sem nome", "link-name", ("pessoas cegas", "pessoas idosas")),
    ],
    "plugin_resolve_parcialmente": ["contraste de cores"],
    "exige_ajuste_no_codigo": ["imagens sem texto alternativo"],
    "indicios_visuais": [],
    "observacao_honestidade": "Ferramentas automáticas encontram só parte das barreiras.",
    "descontos_nota": [],
    "versao_nota": "1.0",
    "raciocinio_resumido": "ok",
}
PAGINAS = [
    {
        "url": HOME,
        "status": "ok",
        "prints": {"desktop": PRINT},
        "axe": {
            "violacoes": [
                {
                    "regra": "image-alt",
                    "gravidade": "critico",
                    "ocorrencias": 3,
                    "caixa": {"x": 683, "y": 192, "largura": 273, "altura": 77},
                },
                {"regra": "link-name", "gravidade": "grave", "ocorrencias": 2, "caixa": None},
                {"regra": "color-contrast", "gravidade": "grave", "ocorrencias": 9},
            ]
        },
        "teclado": {"link_pular_conteudo": False},
        "responsivo_320": {},
    }
]


def _dados(**mudancas):
    base = dict(
        nome="Hospital H",
        dominio="h.com.br",
        setor="saude",
        nota=53,
        analise=ANALISE,
        paginas=PAGINAS,
        prints={PRINT: PNG},
        media_setor=None,
        sites_no_setor=0,
        gerado_em=datetime(2026, 10, 25, 15, 0, tzinfo=UTC),
    )
    base.update(mudancas)
    return DadosRelatorio(**base)


# --- Conteúdo ----------------------------------------------------------------


def test_tres_acoes_com_uma_gratuita_primeiro():
    acoes = escolher_acoes([_pr("image-alt"), _pr("color-contrast", "grave")], ["contraste de cores"])
    assert len(acoes) == 3
    assert acoes[0]["gratuita"] is True and "texto alternativo" in acoes[0]["acao"]
    assert "contraste" in acoes[1]["acao"]
    assert "tecnologia assistiva" in acoes[2]["acao"] and "não substitui" in acoes[2]["acao"]


def test_sem_problema_com_acao_gratuita_usa_a_padrao():
    acoes = escolher_acoes([_pr("color-contrast", "grave")], [])
    assert acoes[0]["gratuita"] is True and "tecla Tab" in acoes[0]["acao"]
    assert "avaliação manual" in acoes[2]["acao"]
    assert len({a["acao"] for a in acoes}) == 3


def test_media_do_setor_so_com_base_suficiente():
    assert "Ainda não há base suficiente" in comparacao_setor("saude", 61.4, 4)
    assert (
        comparacao_setor("saude", 61.4, 12)
        == "Média de saúde na base da Sinal Link: 61 de 100 (12 sites analisados)."
    )


def test_contexto_com_print_anotado_e_grupos_sem_repetir():
    ctx = montar_contexto(_dados())
    primeiro, segundo = ctx["achados"]
    assert primeiro["caixa"] == {"left": 50.0, "top": 25.0, "width": 19.99, "height": 10.03}
    assert "destacado" in primeiro["alt_print"]
    assert segundo["caixa"] is None and "destacado" not in segundo["alt_print"]
    assert ctx["quem_e_afetado"] == ["pessoas cegas", "pessoas idosas"]
    assert ctx["faixa"] == "Barreiras que merecem atenção"
    assert ctx["data"] == "25 de outubro de 2026"


def test_html_acessivel_e_honesto():
    html = gerar_html(_dados())
    assert '<html lang="pt-BR">' in html
    assert "<title>Diagnóstico de acessibilidade digital — Hospital H</title>" in html
    assert 'alt="Sinal Link Acessibilidade"' in html
    assert "Gratuita, sua equipe pode fazer" in html
    assert "só parte das barreiras" in html


def test_texto_com_promessa_proibida_barra_o_relatorio():
    analise = {**ANALISE, "top3_para_leigos": [_achado("Com o plugin seu site fica 100% acessível")]}
    with pytest.raises(RelatorioDesonesto):
        gerar_html(_dados(analise=analise))


def _pdf_disponivel() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        return False
    return True


@pytest.mark.skipif(not _pdf_disponivel(), reason="WeasyPrint precisa do Pango no sistema")
def test_pdf_uma_pagina_com_tags_idioma_titulo_e_fonte_da_marca():
    from pypdf import PdfReader

    from slp_workers.documents.relatorio import gerar_pdf

    pdf = gerar_pdf(gerar_html(_dados(analise={**ANALISE, "top3_para_leigos": [_achado()] * 3})))
    leitor = PdfReader(io.BytesIO(pdf))
    raiz = leitor.trailer["/Root"]
    assert len(leitor.pages) == 1
    assert "/StructTreeRoot" in raiz  # PDF com tags (PDF/UA-1)
    assert raiz["/Lang"] == "pt-BR"
    assert leitor.metadata.title == "Diagnóstico de acessibilidade digital — Hospital H"
    fontes = {
        str(f.get_object()["/BaseFont"]) for p in leitor.pages for f in p["/Resources"]["/Font"].values()
    }
    assert any("DM-Sans" in f for f in fontes)


# --- Orquestração ------------------------------------------------------------


def _analisada(engine, setor="saude", nota=53, nome="h.com.br", dominio="h.com.br"):
    eid = inserir_empresa(engine, nome=nome, dominio=dominio, estado="QUALIFICANDO")
    aid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(empresas.update().where(empresas.c.id == eid).values(setor=setor))
        conn.execute(
            auditorias.insert().values(
                id=aid,
                empresa_id=eid,
                nota=nota,
                totais_json={},
                achados_json=ANALISE,
                paginas_json=PAGINAS,
                artefatos_urls=[PRINT],
                criado_em=datetime.now(UTC),
            )
        )
    return eid, aid


@pytest.fixture
def sem_weasyprint(monkeypatch):
    monkeypatch.setattr("slp_workers.orchestrator.relatorio.gerar_pdf", lambda html: b"%PDF-teste")


def test_salva_pdf_e_html_no_caminho_da_auditoria(engine, sem_weasyprint):
    eid, aid = _analisada(engine)
    armazenamento = ArmazenamentoMemoria()
    armazenamento.arquivos["auditorias/h/01-desktop.png"] = PNG

    caminho = asyncio.run(gerar_e_salvar(engine, armazenamento, eid))

    assert caminho == f"s3://teste/{chave_relatorio(eid, aid, 'pdf')}"
    assert armazenamento.arquivos[chave_relatorio(eid, aid, "pdf")] == b"%PDF-teste"
    html = armazenamento.arquivos[chave_relatorio(eid, aid, "html")].decode()
    assert "data:image/png;base64," in html  # print embutido: a versão web não depende do MinIO
    assert "Ainda não há base suficiente" in html


def test_media_do_setor_usa_outras_empresas_do_mesmo_setor(engine, sem_weasyprint):
    for i, nota in enumerate([40, 50, 60, 70, 80]):
        _analisada(engine, nota=nota, nome=f"s{i}.com.br", dominio=f"s{i}.com.br")
    _analisada(engine, setor="educacao", nota=10, nome="e.com.br", dominio="e.com.br")
    eid, aid = _analisada(engine)
    armazenamento = ArmazenamentoMemoria()
    asyncio.run(gerar_e_salvar(engine, armazenamento, eid))
    html = armazenamento.arquivos[chave_relatorio(eid, aid, "html")].decode()
    assert "Média de saúde na base da Sinal Link: 60 de 100 (5 sites analisados)." in html


def test_sem_analise_nao_gera(engine, sem_weasyprint):
    eid = inserir_empresa(engine, estado="AUDITANDO")
    assert asyncio.run(gerar_e_salvar(engine, ArmazenamentoMemoria(), eid)) is None


class ArmazenamentoQuebrado(ArmazenamentoMemoria):
    async def salvar(self, chave, dados, tipo):
        raise ConnectionError("MinIO fora do ar")


def _tipos(engine, eid):
    with engine.connect() as conn:
        return [r.tipo for r in conn.execute(select(eventos.c.tipo).where(eventos.c.empresa_id == eid))]


def test_evento_de_relatorio_pronto_e_de_falha(engine, sem_weasyprint):
    eid, _ = _analisada(engine)
    assert asyncio.run(gerar_com_evento(engine, ArmazenamentoMemoria(), eid)) is True
    assert _tipos(engine, eid) == ["relatorio_pronto"]

    eid2, _ = _analisada(engine, nome="b.com.br", dominio="b.com.br")
    assert asyncio.run(gerar_com_evento(engine, ArmazenamentoQuebrado(), eid2)) is False
    assert _tipos(engine, eid2) == ["relatorio_falhou"]
