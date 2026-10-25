"""Leitor de site para o Pesquisador: robots.txt, ritmo, limites de tempo e tamanho, só o próprio domínio."""

import re
import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from slp_workers.web.dominio import pertence_ao_dominio
from slp_workers.web.ratelimit import Limitador
from slp_workers.web.safety import HostBloqueado, Resolvedor, exigir_host_publico, resolver_dns

MAX_REDIRECIONAMENTOS = 5
TIPOS_HTML = ("text/html", "application/xhtml+xml")
EXTENSOES_IGNORADAS = re.compile(
    r"\.(pdf|jpe?g|png|gif|webp|svg|ico|zip|rar|docx?|xlsx?|pptx?|mp4|mp3|css|js|xml|json)$", re.I
)

# Páginas institucionais que mais informam o dossiê, na ordem de prioridade. Dentro de cada categoria,
# vale o termo que aparece primeiro na lista e, no empate, o caminho mais curto (/quem-somos antes de
# /quem-somos/faca-uma-doacao). Inclusão vem antes de ESG: é o tema da Sinal Link.
CATEGORIAS_PAGINAS: list[tuple[str, tuple[str, ...]]] = [
    (
        "sobre",
        (
            "quem-somos",
            "quem somos",
            "sobre",
            "institucional",
            "a-empresa",
            "nossa-historia",
            "historia",
            "missao",
            "about",
        ),
    ),
    ("inclusao", ("acessibilidade", "inclusao", "diversidade", "pcd", "pessoas com deficiencia")),
    ("esg", ("esg", "sustentabilidade", "responsabilidade-social", "responsabilidade social", "governanca")),
    ("carreiras", ("trabalhe-conosco", "trabalhe conosco", "carreiras", "vagas", "careers")),
    ("ofertas", ("servicos", "produtos", "solucoes", "cursos", "especialidades", "unidades")),
    ("contato", ("contato", "fale-conosco", "fale conosco", "atendimento")),
]

# Plataforma do site (dossiê, §7.3). Plugins de acessibilidade são detectados pelo Auditor (§8.1).
ASSINATURAS_TECNOLOGIA: list[tuple[str, re.Pattern[str]]] = [
    ("WordPress", re.compile(r"wp-content|wp-includes", re.I)),
    ("VTEX", re.compile(r"vteximg|vtexassets|vtex\.com", re.I)),
    ("Shopify", re.compile(r"cdn\.shopify\.com", re.I)),
    ("Wix", re.compile(r"wixstatic\.com|static\.parastorage\.com", re.I)),
    ("Next.js", re.compile(r"/_next/static", re.I)),
    ("Nuxt", re.compile(r"/_nuxt/", re.I)),
    ("Drupal", re.compile(r"/sites/default/files|drupal-settings-json", re.I)),
    ("Magento", re.compile(r"mage/cookies|/static/frontend/", re.I)),
]


class LeituraBloqueada(Exception):
    """A página não pode ser lida (robots.txt, endereço interno, outro domínio, tipo ou erro)."""


@dataclass
class Link:
    url: str
    texto: str


@dataclass
class Pagina:
    url: str
    titulo: str
    descricao: str
    idioma: str
    texto: str
    links: list[Link] = field(default_factory=list)
    tecnologias: list[str] = field(default_factory=list)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _url_canonica(url: str) -> str:
    partes = urlsplit(url)
    caminho = partes.path or "/"
    return urlunsplit((partes.scheme, partes.netloc.lower(), caminho, partes.query, ""))


def extrair_pagina(url: str, html: str, dominio: str, max_chars: int) -> Pagina:
    soup = BeautifulSoup(html, "html.parser")
    tecnologias = [nome for nome, padrao in ASSINATURAS_TECNOLOGIA if padrao.search(html)]
    gerador = soup.find("meta", attrs={"name": "generator"})
    if gerador and gerador.get("content"):
        tecnologias.append(str(gerador["content"]).strip()[:60])

    links: list[Link] = []
    vistos: set[str] = set()
    for a in soup.find_all("a", href=True):
        destino = _url_canonica(urljoin(url, str(a["href"])))
        partes = urlsplit(destino)
        if partes.scheme not in ("http", "https") or not pertence_ao_dominio(partes.hostname, dominio):
            continue
        if EXTENSOES_IGNORADAS.search(partes.path) or destino in vistos:
            continue
        vistos.add(destino)
        links.append(Link(url=destino, texto=" ".join(a.get_text(" ", strip=True).split())[:80]))

    for tag in soup(["script", "style", "noscript", "svg", "template", "iframe"]):
        tag.decompose()
    titulo = " ".join((soup.title.get_text() if soup.title else "").split())[:200]
    meta = soup.find("meta", attrs={"name": "description"})
    descricao = " ".join(str(meta.get("content", "")).split())[:400] if meta else ""
    html_tag = soup.find("html")
    idioma = str(html_tag.get("lang", "")) if html_tag else ""
    texto = " ".join(soup.get_text(" ", strip=True).split())[:max_chars]

    return Pagina(
        url=url,
        titulo=titulo,
        descricao=descricao,
        idioma=idioma,
        texto=texto,
        links=links,
        tecnologias=sorted(set(tecnologias)),
    )


Categorias = list[tuple[str, tuple[str, ...]]]


def escolher_paginas(home: Pagina, maximo: int, categorias: Categorias | None = None) -> list[str]:
    """Uma página por categoria institucional, na ordem de prioridade, sem repetir a home."""
    home_url = _url_canonica(home.url)
    escolhidas: list[str] = []
    for _categoria, termos in categorias or CATEGORIAS_PAGINAS:
        if len(escolhidas) >= maximo:
            break
        melhor: tuple[int, int, int, str] | None = None
        for link in home.links:
            if link.url in escolhidas or link.url == home_url:
                continue
            caminho = urlsplit(link.url).path.rstrip("/")
            alvo = _sem_acento(f"{caminho} {link.texto}")
            posicoes = [i for i, termo in enumerate(termos) if _sem_acento(termo) in alvo]
            if not posicoes:
                continue
            chave = (posicoes[0], caminho.count("/"), len(caminho), link.url)
            if melhor is None or chave < melhor:
                melhor = chave
        if melhor is not None:
            escolhidas.append(melhor[3])
    return escolhidas


class LeitorSite:
    """Lê páginas de um único domínio. Use `async with LeitorSite(...) as leitor`."""

    def __init__(
        self,
        dominio: str,
        limitador: Limitador,
        *,
        user_agent: str,
        timeout_s: float,
        max_bytes: int,
        max_chars: int,
        permitir_privados: bool = False,
        resolvedor: Resolvedor = resolver_dns,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.dominio = dominio
        self._limitador = limitador
        self._user_agent = user_agent
        self._agente_robots = user_agent.split("/")[0]
        self._max_bytes = max_bytes
        self._max_chars = max_chars
        self._permitir_privados = permitir_privados
        self._resolvedor = resolvedor
        self._robots: dict[str, RobotFileParser] = {}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"},
            timeout=httpx.Timeout(timeout_s),
            follow_redirects=False,
            transport=transport,
        )
        self.requisicoes = 0

    async def __aenter__(self) -> "LeitorSite":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self._client.aclose()

    async def _checar_destino(self, url: str) -> None:
        host = urlsplit(url).hostname
        if not pertence_ao_dominio(host, self.dominio):
            raise LeituraBloqueada(f"redireciona para outro domínio ({host})")
        if not self._permitir_privados:
            try:
                await exigir_host_publico(host or "", self._resolvedor)
            except HostBloqueado as exc:
                raise LeituraBloqueada(str(exc)) from exc

    async def _get(self, url: str) -> httpx.Response:
        """GET com ritmo de 1 req/s, redirecionamentos verificados um a um e corpo limitado."""
        atual = url
        for _ in range(MAX_REDIRECIONAMENTOS + 1):
            await self._checar_destino(atual)
            await self._limitador.aguardar(self.dominio)
            self.requisicoes += 1
            async with self._client.stream("GET", atual) as resposta:
                if resposta.is_redirect:
                    atual = urljoin(atual, resposta.headers.get("location", ""))
                    continue
                corpo = bytearray()
                async for parte in resposta.aiter_bytes():
                    corpo.extend(parte)
                    if len(corpo) > self._max_bytes:
                        break
                # O corpo já vem descompactado: tira os cabeçalhos que fariam o httpx decodificar de novo
                cabecalhos = {
                    k: v
                    for k, v in resposta.headers.items()
                    if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
                }
                return httpx.Response(
                    resposta.status_code,
                    headers=cabecalhos,
                    content=bytes(corpo[: self._max_bytes]),
                    request=httpx.Request("GET", atual),
                )
        raise LeituraBloqueada("redirecionamentos demais")

    async def _robots_para(self, url: str) -> RobotFileParser:
        partes = urlsplit(url)
        origem = f"{partes.scheme}://{partes.netloc}"
        if origem not in self._robots:
            parser = RobotFileParser()
            try:
                r = await self._get(f"{origem}/robots.txt")
                if r.status_code in (401, 403):
                    parser.disallow_all = True
                elif r.status_code >= 500:
                    # Servidor com erro: na dúvida, não lemos (mesma postura dos buscadores)
                    parser.disallow_all = True
                elif r.status_code >= 400:
                    parser.allow_all = True
                else:
                    parser.parse(r.text.splitlines())
            except (httpx.HTTPError, LeituraBloqueada):
                parser.disallow_all = True
            parser.modified()
            self._robots[origem] = parser
        return self._robots[origem]

    async def permitido(self, url: str) -> bool:
        return (await self._robots_para(url)).can_fetch(self._agente_robots, url)

    async def ler(self, url: str) -> Pagina:
        # Endereço interno ou outro domínio é recusado antes até de pedir o robots.txt
        await self._checar_destino(url)
        if not await self.permitido(url):
            raise LeituraBloqueada("o robots.txt do site não permite a leitura automática desta página")
        try:
            r = await self._get(url)
        except httpx.HTTPError as exc:
            raise LeituraBloqueada(f"erro de conexão ({type(exc).__name__})") from exc
        if r.status_code >= 400:
            raise LeituraBloqueada(f"o site respondeu {r.status_code}")
        tipo = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if tipo and tipo not in TIPOS_HTML:
            raise LeituraBloqueada(f"conteúdo não é uma página ({tipo})")
        return extrair_pagina(str(r.request.url), r.text, self.dominio, self._max_chars)

    async def ler_home(self) -> Pagina:
        """Tenta HTTPS e, se a conexão falhar, HTTP."""
        ultimo_erro: LeituraBloqueada | None = None
        for esquema in ("https", "http"):
            try:
                return await self.ler(f"{esquema}://{self.dominio}/")
            except LeituraBloqueada as exc:
                ultimo_erro = exc
                if "robots.txt" in str(exc):
                    break
        assert ultimo_erro is not None
        raise ultimo_erro
