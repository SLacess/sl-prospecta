"""Auditor técnico com Chromium de verdade contra um site de exemplo local com barreiras conhecidas.

Roda no job "Auditor (navegador real)" do CI e no contêiner do worker-audit:
    AUDIT_BROWSER_TESTS=1 AUDIT_AXE_PATH=vendor/axe.min.js pytest tests/test_auditor_navegador.py
"""

import asyncio
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from slp_workers.audit.artefatos import ArmazenamentoMemoria
from slp_workers.audit.engine import Auditor
from slp_workers.settings import WorkerConfig
from slp_workers.web.fetcher import LeituraBloqueada
from slp_workers.web.ratelimit import LimitadorMemoria

AXE = os.environ.get("AUDIT_AXE_PATH", str(Path(__file__).resolve().parents[1] / "vendor" / "axe.min.js"))
pytestmark = pytest.mark.skipif(
    not os.environ.get("AUDIT_BROWSER_TESTS") or not Path(AXE).exists(),
    reason="precisa de Chromium (playwright install) e do axe-core (scripts/baixar_axe.py)",
)

MENU = (
    '<nav><a href="/contato">Contato</a> <a href="/cursos">Cursos</a> <a href="/login">Área do aluno</a> '
    '<a href="/trabalhe-conosco">Trabalhe conosco</a></nav>'
)


def pagina(titulo, corpo, cabeca="", lang=' lang="pt-BR"'):
    return (
        f"<!doctype html><html{lang}><head><meta charset='utf-8'><title>{titulo}</title>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>{cabeca}</head>"
        f"<body>{corpo}</body></html>"
    )


def site(porta_segredo: int) -> dict[str, tuple[int, str, str]]:
    return {
        "/robots.txt": (200, "text/plain", "User-agent: *\nDisallow: /trabalhe-conosco\n"),
        # Home com barreiras: imagem sem alt, contraste baixo, foco sem contorno, estouro em 320 px,
        # sem link "pular para o conteúdo" e um plugin de acessibilidade instalado
        "/": (
            200,
            "text/html",
            pagina(
                "Faculdade Exemplo",
                MENU + '<main><img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="40" height="40">'
                '<p style="color:#bbb;background:#fff">Texto com pouco contraste</p>'
                '<div style="width:900px">Faixa larga demais para celular</div>'
                "<button>Inscreva-se</button>"
                '<h1>Faculdade Exemplo</h1><h3>Notícias</h3><a href="/noticia">Saiba mais</a></main>',
                cabeca='<style>*:focus{outline:none}</style><script src="https://cdn.userway.org/widget.js"></script>',
            ),
        ),
        # Contato: campos sem rótulo e foco preso no formulário
        "/contato": (
            200,
            "text/html",
            pagina(
                "Contato",
                MENU + '<main><h1>Contato</h1><form><input id="a"><input id="b"><input id="c"></form></main>'
                "<script>document.addEventListener('keydown', (e) => {"
                "if (e.key === 'Tab' && document.activeElement.id === 'c') {"
                "e.preventDefault(); document.getElementById('a').focus(); }});</script>",
            ),
        ),
        # Cursos: página correta, para conferir que o Auditor não acusa o que não existe
        "/cursos": (
            200,
            "text/html",
            pagina(
                "Cursos",
                '<a href="#conteudo">Pular para o conteúdo</a>'
                + MENU.replace("<nav>", '<nav aria-label="Menu">')
                + '<main id="conteudo"><h1>Cursos</h1><p>Direito, Medicina e Engenharia.</p>'
                '<label for="busca">Buscar curso</label><input id="busca" type="search"></main>',
                cabeca="<style>a{display:inline-block;padding:12px 8px}</style>",
            ),
        ),
        # Login: tenta alcançar serviços internos (deve ser bloqueado pelo filtro de rede)
        "/login": (
            200,
            "text/html",
            pagina(
                "Área do aluno",
                MENU
                + f'<main><h1>Área do aluno</h1><img alt="" src="http://localhost:{porta_segredo}/segredo.png">'
                f"<script>fetch('http://localhost:{porta_segredo}/api').catch(() => {{}});"
                "fetch('http://169.254.169.254/latest/meta-data').catch(() => {});</script></main>",
            ),
        ),
        "/trabalhe-conosco": (200, "text/html", pagina("Vagas", "<h1>Vagas</h1>")),
    }


class Servidor:
    def __init__(self, rotas=None, atraso_s: float = 0):
        self.rotas = rotas or {}
        self.requisicoes: list[str] = []
        dono = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                dono.requisicoes.append(self.path)
                if atraso_s:
                    time.sleep(atraso_s)
                status, tipo, corpo = dono.rotas.get(
                    self.path.split("?")[0], (404, "text/plain", "não encontrado")
                )
                dados = corpo.encode()
                self.send_response(status)
                self.send_header("Content-Type", f"{tipo}; charset=utf-8")
                self.send_header("Content-Length", str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *_args):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.porta = self.http.server_address[1]
        threading.Thread(target=self.http.serve_forever, daemon=True).start()

    def fechar(self):
        self.http.shutdown()


async def _resolvedor(host):
    # Tudo que não é o site de teste conta como interno: o teste não sai para a internet
    return ["10.0.0.1"]


def _auditor(config, armazenamento, origem):
    return Auditor(
        config,
        LimitadorMemoria(intervalo_s=0),
        armazenamento,
        resolvedor=_resolvedor,
        hosts_liberados={"127.0.0.1"},
        origem=origem,
    )


@pytest.fixture(scope="module")
def auditoria():
    segredo = Servidor(
        {"/segredo.png": (200, "image/png", "SEGREDO"), "/api": (200, "text/plain", "SEGREDO")}
    )
    alvo = Servidor()
    alvo.rotas = site(segredo.porta)
    config = WorkerConfig(audit_axe_path=AXE, audit_page_timeout_s=30)
    armazenamento = ArmazenamentoMemoria()
    progresso: list[tuple[int, int, str]] = []

    async def ao_progresso(i, total, caminho):
        progresso.append((i, total, caminho))

    origem = f"http://127.0.0.1:{alvo.porta}"
    resultado = asyncio.run(
        _auditor(config, armazenamento, origem).auditar("127.0.0.1", "auditorias/teste", ao_progresso)
    )
    yield resultado, armazenamento, progresso, segredo
    alvo.fechar()
    segredo.fechar()


def _pagina(resultado, caminho):
    return next(
        p for p in resultado.paginas if p["url"].split(":", 2)[2].split("/", 1)[1] == caminho.lstrip("/")
    )


def _regras(p):
    return {v["regra"] for v in p["axe"]["violacoes"]}


def test_audita_home_e_paginas_chave_com_progresso(auditoria):
    resultado, _, progresso, _ = auditoria
    assert [c for _, _, c in progresso] == ["/", "/contato", "/cursos", "/login", "/trabalhe-conosco"]
    assert all(total == 5 for _, total, _ in progresso)
    assert [p["status"] for p in resultado.paginas] == ["ok", "ok", "ok", "ok", "bloqueada"]
    assert "robots.txt" in resultado.paginas[4]["erro"]


def test_home_tem_as_barreiras_plantadas(auditoria):
    home = _pagina(auditoria[0], "/")
    assert {"image-alt", "color-contrast"} <= _regras(home)
    assert home["teclado"]["link_pular_conteudo"] is False
    assert home["teclado"]["sem_indicador_aparente"] >= 1
    assert home["responsivo_320"]["rolagem_horizontal"] is True
    assert home["responsivo_320"]["estouram"]
    # Camada semântica sem IA (Tarefa 4)
    assert [link["texto"] for link in home["semantica"]["links_genericos"]] == ["Saiba mais"]
    assert home["semantica"]["saltos_de_titulo"] == [{"de": "h1", "para": "h3", "texto": "Notícias"}]


def test_pagina_correta_nao_tem_sinal_semantico(auditoria):
    cursos = _pagina(auditoria[0], "/cursos")
    assert cursos["semantica"] == {"links_genericos": [], "saltos_de_titulo": []}


def test_contato_tem_campos_sem_rotulo_e_armadilha_de_foco(auditoria):
    contato = _pagina(auditoria[0], "/contato")
    assert "label" in _regras(contato)
    assert set(contato["teclado"]["armadilha_de_foco"]["elementos"]) == {"input#a", "input#b", "input#c"}


def test_pagina_correta_nao_gera_falso_positivo(auditoria):
    cursos = _pagina(auditoria[0], "/cursos")
    assert cursos["axe"]["violacoes"] == []
    assert cursos["teclado"]["link_pular_conteudo"] is True
    assert cursos["teclado"]["armadilha_de_foco"] is None
    assert cursos["teclado"]["sem_indicador_aparente"] == 0
    assert cursos["responsivo_320"]["rolagem_horizontal"] is False


def test_plugin_detectado_mesmo_com_o_script_bloqueado(auditoria):
    assert auditoria[0].plugins == ["UserWay"]


def test_pagina_nao_alcanca_servicos_internos(auditoria):
    assert auditoria[3].requisicoes == []


def test_prints_desktop_e_320_de_cada_pagina_testada(auditoria):
    resultado, armazenamento, _, _ = auditoria
    assert len(armazenamento.arquivos) == 8
    assert all(dados.startswith(b"\x89PNG") for dados in armazenamento.arquivos.values())
    assert len(resultado.artefatos) == 8
    assert resultado.totais()["paginas_auditadas"] == 4


def test_pagina_lenta_esgota_o_tempo():
    lento = Servidor(
        {"/": (200, "text/html", pagina("Lento", "<h1>Lento</h1>")), "/robots.txt": (404, "text/plain", "")},
        atraso_s=4,
    )
    try:
        config = WorkerConfig(audit_axe_path=AXE, audit_page_timeout_s=2)
        auditor = _auditor(config, ArmazenamentoMemoria(), f"http://127.0.0.1:{lento.porta}")

        async def nada(*_):
            pass

        with pytest.raises(LeituraBloqueada, match="tempo esgotado"):
            asyncio.run(auditor.auditar("127.0.0.1", "x", nada))
    finally:
        lento.fechar()
