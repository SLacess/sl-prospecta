"""Motor do Auditor técnico (CONSTITUICAO §8.1 e §8.4).

Abre a home e até 4 páginas-chave num Chromium headless e, em cada uma: axe-core (WCAG 2.2 AA),
teste de teclado, teste em 320 px, prints e detecção de plugin de acessibilidade.
Devolve o resultado ao orquestrador; não grava no banco (§6).

Regras de raspagem (§8.4):
- robots.txt e 1 abertura de página por segundo por domínio (os recursos que a página carrega vêm junto);
- só páginas públicas: nada é clicado, preenchido ou enviado; login e checkout são só abertos;
- 45 s por página;
- toda requisição do navegador passa por um filtro que bloqueia endereços internos (SSRF).
"""

import asyncio
import ipaddress
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from slp_workers.audit.artefatos import Armazenamento
from slp_workers.audit.axe import rodar_axe
from slp_workers.audit.plugins import JS_SINAIS, detectar_plugins
from slp_workers.audit.responsivo import testar_320
from slp_workers.audit.teclado import testar_teclado
from slp_workers.settings import WorkerConfig
from slp_workers.web.dominio import pertence_ao_dominio
from slp_workers.web.fetcher import Categorias, LeitorSite, LeituraBloqueada, Link, Pagina, escolher_paginas
from slp_workers.web.ratelimit import Limitador
from slp_workers.web.safety import HostBloqueado, Resolvedor, exigir_host_publico, resolver_dns

log = logging.getLogger("slp_workers.audit")

# Páginas-chave do §8.1, na ordem de prioridade
CATEGORIAS_AUDITORIA: Categorias = [
    ("contato", ("contato", "fale-conosco", "fale conosco", "atendimento")),
    ("produto", ("cursos", "curso", "produtos", "servicos", "especialidades", "solucoes", "planos")),
    ("login", ("login", "entrar", "acesse", "portal", "area-do-cliente", "area do cliente", "minha-conta")),
    ("checkout", ("carrinho", "checkout", "cart", "sacola")),
    ("carreiras", ("trabalhe-conosco", "trabalhe conosco", "carreiras", "vagas")),
]

JS_LINKS = """() => [...document.querySelectorAll("a[href]")].slice(0, 500).map((a) => ({
  href: a.href,
  texto: (a.innerText || a.getAttribute("aria-label") || "").trim().replace(/\\s+/g, " ").slice(0, 80),
}))"""

Progresso = Callable[[int, int, str], Awaitable[None]]


@dataclass
class ResultadoAuditoria:
    dominio: str
    paginas: list[dict[str, Any]] = field(default_factory=list)
    plugins: list[str] = field(default_factory=list)
    artefatos: list[str] = field(default_factory=list)

    @property
    def auditadas(self) -> list[dict[str, Any]]:
        return [p for p in self.paginas if p["status"] == "ok"]

    def totais(self) -> dict[str, int]:
        """Contagem do §8.2: uma regra violada numa página = 1 problema, separado por gravidade."""
        totais = {"critico": 0, "grave": 0, "moderado": 0, "leve": 0}
        ocorrencias = 0
        regras: set[str] = set()
        for p in self.auditadas:
            for v in p["axe"]["violacoes"]:
                totais[v["gravidade"]] += 1
                ocorrencias += v["ocorrencias"]
                regras.add(v["regra"])
        return {
            **totais,
            "ocorrencias": ocorrencias,
            "regras_distintas": len(regras),
            "paginas_auditadas": len(self.auditadas),
            "paginas_com_armadilha_de_foco": sum(
                1 for p in self.auditadas if p["teclado"]["armadilha_de_foco"]
            ),
            "paginas_sem_link_pular_conteudo": sum(
                1 for p in self.auditadas if not p["teclado"]["link_pular_conteudo"]
            ),
            "paginas_com_rolagem_horizontal_320": sum(
                1 for p in self.auditadas if p["responsivo_320"]["rolagem_horizontal"]
            ),
        }


class FiltroRede:
    """Decide, para cada requisição do navegador, se ela pode sair. Cache por host."""

    def __init__(self, permitir_privados: bool, hosts_liberados: set[str], resolvedor: Resolvedor) -> None:
        self._permitir_privados = permitir_privados
        self._liberados = hosts_liberados
        self._resolvedor = resolvedor
        self._cache: dict[str, bool] = {}
        self.bloqueadas: list[str] = []

    async def permitido(self, url: str) -> bool:
        partes = urlsplit(url)
        if partes.scheme in ("data", "blob", "about"):
            return True
        if partes.scheme not in ("http", "https"):
            return False
        host = (partes.hostname or "").lower()
        if host in self._liberados or self._permitir_privados:
            return True
        if host not in self._cache:
            try:
                ipaddress.ip_address(host)
                eh_ip_publico = ipaddress.ip_address(host).is_global
                self._cache[host] = eh_ip_publico
            except ValueError:
                try:
                    await exigir_host_publico(host, self._resolvedor)
                    self._cache[host] = True
                except HostBloqueado:
                    self._cache[host] = False
        if not self._cache[host]:
            self.bloqueadas.append(f"{partes.scheme}://{host}")
        return self._cache[host]

    async def rota(self, route: Any) -> None:
        if await self.permitido(route.request.url):
            await route.continue_()
        else:
            await route.abort("blockedbyclient")


class Auditor:
    def __init__(
        self,
        config: WorkerConfig,
        limitador: Limitador,
        armazenamento: Armazenamento,
        *,
        resolvedor: Resolvedor = resolver_dns,
        hosts_liberados: set[str] | None = None,
        origem: str | None = None,
    ) -> None:
        self._config = config
        self._limitador = limitador
        self._armazenamento = armazenamento
        self._resolvedor = resolvedor
        self._hosts_liberados = hosts_liberados or set()
        # Só para testes: http://127.0.0.1:PORTA em vez de https://<domínio>
        self._origem = origem

    def _leitor_robots(self, dominio: str) -> LeitorSite:
        cfg = self._config
        return LeitorSite(
            dominio,
            self._limitador,
            user_agent=cfg.crawler_user_agent,
            timeout_s=15,
            max_bytes=200_000,
            max_chars=1000,
            permitir_privados=cfg.web_allow_private_hosts or dominio in self._hosts_liberados,
            resolvedor=self._resolvedor,
        )

    async def auditar(
        self, dominio: str, prefixo_artefatos: str, ao_progresso: Progresso
    ) -> ResultadoAuditoria:
        from playwright.async_api import async_playwright

        cfg = self._config
        resultado = ResultadoAuditoria(dominio=dominio)
        filtro = FiltroRede(cfg.web_allow_private_hosts, self._hosts_liberados, self._resolvedor)

        async with self._leitor_robots(dominio) as robots, async_playwright() as pw:
            navegador = await pw.chromium.launch(args=["--disable-dev-shm-usage"])
            try:
                contexto = await navegador.new_context(
                    user_agent=cfg.crawler_user_agent,
                    locale="pt-BR",
                    viewport={"width": 1366, "height": 768},
                    service_workers="block",
                    accept_downloads=False,
                )
                await contexto.route("**/*", filtro.rota)
                pagina = await contexto.new_page()

                home_url = await self._abrir_home(pagina, robots, dominio)
                links = await pagina.evaluate(JS_LINKS)
                home = Pagina(
                    url=home_url,
                    titulo="",
                    descricao="",
                    idioma="",
                    texto="",
                    links=[
                        Link(url=item["href"].split("#")[0], texto=item["texto"])
                        for item in links
                        if pertence_ao_dominio(urlsplit(item["href"]).hostname, dominio)
                    ],
                )
                urls = [home_url, *escolher_paginas(home, cfg.audit_max_pages - 1, CATEGORIAS_AUDITORIA)]

                plugins: set[str] = set()
                for i, url in enumerate(urls, start=1):
                    caminho = urlsplit(url).path or "/"
                    await ao_progresso(i, len(urls), caminho)
                    dados = await self._auditar_pagina(
                        pagina, robots, url, i, prefixo_artefatos, dominio, ja_aberta=i == 1
                    )
                    plugins.update(dados.pop("_plugins", []))
                    resultado.paginas.append(dados)
                    resultado.artefatos.extend(u for u in dados["prints"].values() if u)
                resultado.plugins = sorted(plugins)
            finally:
                await navegador.close()

        if filtro.bloqueadas:
            log.info("%s: %d requisições a endereços internos bloqueadas", dominio, len(filtro.bloqueadas))
        return resultado

    async def _abrir_home(self, pagina: Any, robots: LeitorSite, dominio: str) -> str:
        """Abre a home (HTTPS e, se falhar, HTTP) respeitando robots.txt e o ritmo por domínio."""
        origens = [self._origem] if self._origem else [f"https://{dominio}", f"http://{dominio}"]
        ultimo: Exception | None = None
        for origem in origens:
            url = f"{origem}/"
            try:
                await self._navegar(pagina, robots, url, dominio)
                return pagina.url
            except LeituraBloqueada as exc:
                ultimo = exc
                if "robots.txt" in str(exc):
                    break
        raise LeituraBloqueada(str(ultimo))

    async def _navegar(self, pagina: Any, robots: LeitorSite, url: str, dominio: str) -> None:
        from playwright.async_api import Error as ErroPlaywright

        if not await robots.permitido(url):
            raise LeituraBloqueada("o robots.txt do site não permite a leitura automática desta página")
        await self._limitador.aguardar(dominio)
        timeout_ms = self._config.audit_page_timeout_s * 1000
        try:
            resposta = await pagina.goto(url, wait_until="load", timeout=timeout_ms)
        except ErroPlaywright as exc:
            texto = str(exc).split("\n")[0]
            raise LeituraBloqueada(
                "tempo esgotado" if "Timeout" in texto else f"erro ao abrir ({texto[:120]})"
            ) from exc
        if resposta is not None and resposta.status >= 400:
            raise LeituraBloqueada(f"o site respondeu {resposta.status}")
        if not pertence_ao_dominio(urlsplit(pagina.url).hostname, dominio):
            raise LeituraBloqueada(f"redireciona para outro domínio ({urlsplit(pagina.url).hostname})")
        try:
            await pagina.wait_for_load_state("networkidle", timeout=5000)
        except ErroPlaywright:
            pass  # sites com conexões abertas (chat, analytics) nunca ficam ociosos

    async def _auditar_pagina(
        self,
        pagina: Any,
        robots: LeitorSite,
        url: str,
        indice: int,
        prefixo: str,
        dominio: str,
        ja_aberta: bool,
    ) -> dict[str, Any]:
        base: dict[str, Any] = {"url": url, "prints": {}}
        try:
            return await asyncio.wait_for(
                self._testar(pagina, robots, url, indice, prefixo, dominio, ja_aberta, base),
                timeout=self._config.audit_page_timeout_s,
            )
        except TimeoutError:
            return {**base, "status": "tempo_esgotado", "erro": "a página passou de 45 s"}
        except LeituraBloqueada as exc:
            return {**base, "status": "bloqueada", "erro": str(exc)}

    async def _testar(
        self,
        pagina: Any,
        robots: LeitorSite,
        url: str,
        indice: int,
        prefixo: str,
        dominio: str,
        ja_aberta: bool,
        base: dict[str, Any],
    ) -> dict[str, Any]:
        if not ja_aberta:
            await self._navegar(pagina, robots, url, dominio)
        titulo = await pagina.title()
        print_desktop = await pagina.screenshot(type="png")
        axe = await rodar_axe(pagina, self._config.audit_axe_path)
        plugins = detectar_plugins(await pagina.evaluate(JS_SINAIS))
        teclado = await testar_teclado(pagina, self._config.audit_tab_presses)
        responsivo, print_320 = await testar_320(pagina)
        prints = {
            "desktop": await self._armazenamento.salvar_png(
                f"{prefixo}/{indice:02d}-desktop.png", print_desktop
            ),
            "320px": await self._armazenamento.salvar_png(f"{prefixo}/{indice:02d}-320px.png", print_320),
        }
        return {
            **base,
            "url": pagina.url,
            "status": "ok",
            "titulo": titulo[:200],
            "axe": axe,
            "teclado": teclado,
            "responsivo_320": responsivo,
            "prints": prints,
            "plugins": plugins,
            "_plugins": plugins,
        }
