import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ.pop("ANTHROPIC_API_KEY", None)

import uuid  # noqa: E402
from decimal import Decimal  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from slp_workers.agents.researcher import Dossie, Localizacao, Mencao, Sinal  # noqa: E402
from slp_workers.db import empresas, metadata  # noqa: E402
from slp_workers.llm import Consumo, ErroIA, RespostaBusca  # noqa: E402
from slp_workers.settings import WorkerConfig  # noqa: E402
from slp_workers.web.ratelimit import LimitadorMemoria  # noqa: E402

DOMINIO = "exemplo.com.br"
HOME = f"https://{DOMINIO}/"
SOBRE = f"https://{DOMINIO}/quem-somos"
ESG = f"https://{DOMINIO}/sustentabilidade"


def html(titulo: str, corpo: str, links: str = "") -> str:
    return (
        f'<html lang="pt-BR"><head><title>{titulo}</title>'
        f'<meta name="description" content="Desc {titulo}"></head>'
        f"<body><nav>{links}</nav><main>{corpo}</main><script>var x=1;</script></body></html>"
    )


HOME_HTML = html(
    "Hospital Exemplo",
    "<h1>Hospital Exemplo</h1><p>Atendimento de alta complexidade em Sorocaba.</p>"
    '<img src="/wp-content/uploads/logo.png">',
    '<a href="/quem-somos">Quem somos</a><a href="/sustentabilidade">Sustentabilidade</a>'
    '<a href="/trabalhe-conosco">Trabalhe conosco</a><a href="https://facebook.com/x">Facebook</a>'
    '<a href="/manual.pdf">Manual</a>',
)
SITE_PADRAO: dict[str, tuple[int, dict, str]] = {
    f"https://{DOMINIO}/robots.txt": (200, {"content-type": "text/plain"}, "User-agent: *\nAllow: /\n"),
    HOME: (200, {"content-type": "text/html; charset=utf-8"}, HOME_HTML),
    SOBRE: (
        200,
        {"content-type": "text/html"},
        html("Quem somos", "<p>Fundado em 1950, sede em Sorocaba/SP.</p>"),
    ),
    ESG: (
        200,
        {"content-type": "text/html"},
        html("ESG", "<p>Programa de inclusão de pessoas com deficiência.</p>"),
    ),
    f"https://{DOMINIO}/trabalhe-conosco": (404, {"content-type": "text/html"}, "não achei"),
}


def transporte(site: dict[str, tuple[int, dict, str]]) -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        status, headers, corpo = site.get(str(request.url), (404, {"content-type": "text/plain"}, ""))
        return httpx.Response(status, headers=headers, text=corpo)

    return httpx.MockTransport(responder)


async def resolvedor_publico(host: str) -> list[str]:
    return ["93.184.216.34"]


def dossie_exemplo(**alteracoes) -> Dossie:
    base = Dossie(
        nome_oficial="Hospital Exemplo S.A.",
        setor="saude",
        subsetor="hospital geral",
        descricao="Hospital de alta complexidade.",
        missao=None,
        produtos_servicos=["internação", "pronto-socorro"],
        publicos_atendidos=["pacientes particulares e de convênios"],
        localizacao=Localizacao(cidade="Sorocaba", uf="sp", url=SOBRE),
        porte_indicios=None,
        mencoes_inclusao=[
            Mencao(tema="pcd", trecho="Programa de inclusão de pessoas com deficiência.", url=ESG)
        ],
        sinais=[Sinal(tipo="outro", descricao="Programa de inclusão", url=ESG + "/")],
        lacunas=["o site não informa número de leitos"],
        resumo_5_linhas=["Linha 1", "Linha 2", "Linha 3", "Linha 4", "Linha 5"],
        raciocinio_resumido="Dados das páginas inicial, quem somos e sustentabilidade.",
    )
    return base.model_copy(update=alteracoes)


class IAFalsa:
    """Substitui a Claude API: devolve respostas prontas e conta as chamadas."""

    def __init__(
        self,
        dossie: Dossie | None = None,
        busca_texto: str = "",
        urls: list[str] | None = None,
        erro: ErroIA | None = None,
    ) -> None:
        self.dossie = dossie or dossie_exemplo()
        self.busca_texto = busca_texto
        self.urls = urls or []
        self.erro = erro
        self.chamadas: list[str] = []
        self.conteudos: list[str] = []

    async def estruturado(self, *, modelo, sistema, conteudo, formato, effort, max_tokens):
        self.chamadas.append("estruturado")
        self.conteudos.append(conteudo)
        if self.erro:
            raise self.erro
        return self.dossie, Consumo(
            modelo=modelo, tokens_in=12000, tokens_out=900, custo_brl=Decimal("0.2100")
        )

    async def com_busca_web(self, *, modelo, sistema, conteudo, max_buscas, effort, max_tokens):
        self.chamadas.append("busca")
        return RespostaBusca(
            texto=self.busca_texto,
            urls_consultadas=self.urls,
            consumo=Consumo(
                modelo=modelo, tokens_in=8000, tokens_out=300, buscas_web=2, custo_brl=Decimal("0.1800")
            ),
        )


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(eng)
    yield eng
    eng.dispose()


def inserir_empresa(engine, nome="exemplo.com.br", dominio: str | None = DOMINIO, estado="NOVO") -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(empresas.insert().values(id=eid, nome=nome, dominio=dominio, estado=estado))
    return eid


@pytest.fixture
def empresa_id(engine):
    return inserir_empresa(engine)


@pytest.fixture
def config():
    return WorkerConfig()


def montar_ctx(engine, ia, site=None, config=None) -> dict:
    return {
        "engine": engine,
        "ia": ia,
        "limitador": LimitadorMemoria(intervalo_s=0),
        "config": config or WorkerConfig(),
        "resolvedor": resolvedor_publico,
        "transport": transporte(site if site is not None else SITE_PADRAO),
    }
