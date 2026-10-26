import asyncio
import time

import pytest

from slp_workers.web.dominio import normalizar_dominio, pertence_ao_dominio
from slp_workers.web.fetcher import LeitorSite, LeituraBloqueada, escolher_paginas, extrair_pagina
from slp_workers.web.ratelimit import LimitadorMemoria
from tests.conftest import DOMINIO, HOME, HOME_HTML, SITE_PADRAO, resolvedor_publico, transporte


def _leitor(site=None, resolvedor=resolvedor_publico, permitir_privados=False, max_bytes=2_000_000):
    return LeitorSite(
        DOMINIO,
        LimitadorMemoria(intervalo_s=0),
        user_agent="SinalLinkA11yAudit/1.0 (+https://x)",
        timeout_s=5,
        max_bytes=max_bytes,
        max_chars=5000,
        permitir_privados=permitir_privados,
        resolvedor=resolvedor,
        transport=transporte(site if site is not None else SITE_PADRAO),
    )


async def _ler(leitor, url):
    async with leitor:
        return await leitor.ler(url)


# --- Extração ----------------------------------------------------------------


def test_extrai_texto_sem_scripts_e_links_do_proprio_dominio():
    p = extrair_pagina(HOME, HOME_HTML, DOMINIO, 5000)
    assert p.titulo == "Hospital Exemplo"
    assert p.idioma == "pt-BR"
    assert "alta complexidade" in p.texto
    assert "var x" not in p.texto
    urls = [link.url for link in p.links]
    assert f"https://{DOMINIO}/quem-somos" in urls
    assert not any("facebook" in u for u in urls)
    assert not any(u.endswith(".pdf") for u in urls)
    assert "WordPress" in p.tecnologias


def test_escolhe_paginas_institucionais_por_prioridade():
    p = extrair_pagina(HOME, HOME_HTML, DOMINIO, 5000)
    escolhidas = escolher_paginas(p, 5)
    assert escolhidas[:3] == [
        f"https://{DOMINIO}/quem-somos",
        f"https://{DOMINIO}/sustentabilidade",
        f"https://{DOMINIO}/trabalhe-conosco",
    ]
    assert escolher_paginas(p, 1) == [f"https://{DOMINIO}/quem-somos"]


# --- Regras de leitura (§8.4) ------------------------------------------------


def test_robots_que_proibe_bloqueia_a_leitura():
    site = dict(SITE_PADRAO)
    site[f"https://{DOMINIO}/robots.txt"] = (
        200,
        {"content-type": "text/plain"},
        "User-agent: SinalLinkA11yAudit\nDisallow: /\n",
    )
    with pytest.raises(LeituraBloqueada, match="robots.txt"):
        asyncio.run(_ler(_leitor(site), HOME))


def test_robots_ausente_permite():
    site = {k: v for k, v in SITE_PADRAO.items() if not k.endswith("robots.txt")}
    assert asyncio.run(_ler(_leitor(site), HOME)).titulo == "Hospital Exemplo"


def test_robots_com_erro_no_servidor_bloqueia():
    site = dict(SITE_PADRAO)
    site[f"https://{DOMINIO}/robots.txt"] = (503, {}, "")
    with pytest.raises(LeituraBloqueada):
        asyncio.run(_ler(_leitor(site), HOME))


def test_redirecionamento_para_outro_dominio_e_barrado():
    site = dict(SITE_PADRAO)
    site[HOME] = (301, {"location": "https://golpe.io/"}, "")
    with pytest.raises(LeituraBloqueada, match="outro domínio"):
        asyncio.run(_ler(_leitor(site), HOME))


def test_redirecionamento_para_www_e_seguido():
    site = dict(SITE_PADRAO)
    site[HOME] = (301, {"location": f"https://www.{DOMINIO}/"}, "")
    site[f"https://www.{DOMINIO}/robots.txt"] = (404, {}, "")
    site[f"https://www.{DOMINIO}/"] = (200, {"content-type": "text/html"}, HOME_HTML)
    assert asyncio.run(_ler(_leitor(site), HOME)).url == f"https://www.{DOMINIO}/"


def test_endereco_interno_e_recusado():
    async def privado(host):
        return ["10.0.0.5"]

    with pytest.raises(LeituraBloqueada, match="não público"):
        asyncio.run(_ler(_leitor(resolvedor=privado), HOME))
    # Liberado só quando configurado para testes locais
    assert asyncio.run(_ler(_leitor(resolvedor=privado, permitir_privados=True), HOME)).titulo


def test_pagina_grande_e_cortada():
    site = dict(SITE_PADRAO)
    site[HOME] = (200, {"content-type": "text/html"}, "<html><body>" + "a" * 50_000 + "</body></html>")
    pagina = asyncio.run(_ler(_leitor(site, max_bytes=1000), HOME))
    assert len(pagina.texto) <= 1000


def test_cabecalho_com_acento_nao_derruba_a_leitura():
    # Servidores reais mandam cabeçalhos em latin-1 (ex.: robots.txt com "Localização: São Paulo")
    site = dict(SITE_PADRAO)
    site[HOME] = (200, {"content-type": "text/html", "x-local": "São Paulo".encode("latin-1")}, HOME_HTML)
    assert asyncio.run(_ler(_leitor(site), HOME)).titulo


def test_conteudo_que_nao_e_pagina_e_recusado():
    site = dict(SITE_PADRAO)
    site[HOME] = (200, {"content-type": "application/pdf"}, "%PDF")
    with pytest.raises(LeituraBloqueada, match="não é uma página"):
        asyncio.run(_ler(_leitor(site), HOME))


def test_uma_requisicao_por_segundo_por_dominio():
    limitador = LimitadorMemoria(intervalo_s=0.2)

    async def tres():
        for _ in range(3):
            await limitador.aguardar(DOMINIO)

    inicio = time.monotonic()
    asyncio.run(tres())
    assert time.monotonic() - inicio >= 0.4


# --- Domínio -----------------------------------------------------------------


@pytest.mark.parametrize("entrada", ["https://www.Exemplo.com.br/x", "exemplo.com.br.", "EXEMPLO.COM.BR:443"])
def test_normaliza_como_a_api(entrada):
    assert normalizar_dominio(entrada) == "exemplo.com.br"


@pytest.mark.parametrize("entrada", ["10.0.0.1", "localhost", "exemplo.c0m", ""])
def test_rejeita_o_que_nao_e_dominio(entrada):
    assert normalizar_dominio(entrada) is None


def test_pertence_ao_dominio():
    assert pertence_ao_dominio("www.exemplo.com.br", DOMINIO)
    assert not pertence_ao_dominio("exemplo.com.br.golpe.io", DOMINIO)
    assert not pertence_ao_dominio("outroexemplo.com.br", DOMINIO)


def test_prefere_a_pagina_principal_e_inclusao_antes_de_esg():
    """Caso real (Sírio-Libanês): /quem-somos/faca-uma-doacao vinha antes de /quem-somos e
    a página de inclusão ficava de fora."""
    html_home = (
        '<a href="/quem-somos/faca-uma-doacao">Faça uma doação</a>'
        '<a href="/quem-somos">Quem somos</a>'
        '<a href="/quem-somos/sustentabilidade-ambiental">Sustentabilidade</a>'
        '<a href="/inclusao-e-diversidade">Inclusão e diversidade</a>'
    )
    p = extrair_pagina(HOME, html_home, DOMINIO, 5000)
    assert escolher_paginas(p, 3) == [
        f"https://{DOMINIO}/quem-somos",
        f"https://{DOMINIO}/inclusao-e-diversidade",
        f"https://{DOMINIO}/quem-somos/sustentabilidade-ambiental",
    ]
