"""Teste de navegação por teclado (CONSTITUICAO §8.1): Tab a Tab, como uma pessoa sem mouse.

Verifica: link "pular para o conteúdo" logo no início, indicador de foco visível em cada parada
e armadilhas de foco (o foco fica preso num grupo pequeno de elementos).
O indicador é aferido pelo estilo calculado (contorno ou sombra); mudanças só de cor de fundo
não são reconhecidas, por isso o resultado fala em indicador "não aparente".
"""

import re
from typing import Any

JS_FOCO = """() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const css = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const caminho = (n) => {
    const partes = [];
    while (n && n.nodeType === 1 && partes.length < 4) {
      let p = n.tagName.toLowerCase();
      if (n.id) { partes.unshift(`${p}#${n.id}`); break; }
      const irmaos = n.parentElement
        ? [...n.parentElement.children].filter((c) => c.tagName === n.tagName)
        : [];
      if (irmaos.length > 1) p += `:nth-of-type(${irmaos.indexOf(n) + 1})`;
      partes.unshift(p);
      n = n.parentElement;
    }
    return partes.join(" > ");
  };
  const larguraContorno = parseFloat(css.outlineWidth) || 0;
  return {
    seletor: caminho(el),
    tag: el.tagName.toLowerCase(),
    texto: (el.getAttribute("aria-label") || el.innerText || el.value || el.getAttribute("title") || "")
      .trim().replace(/\\s+/g, " ").slice(0, 80),
    href: el.getAttribute("href"),
    indicador: (css.outlineStyle !== "none" && larguraContorno > 0) ||
      (css.boxShadow && css.boxShadow !== "none"),
    visivel: r.width > 0 && r.height > 0,
  };
}"""

JS_FOCAVEIS = """() => document.querySelectorAll(
  'a[href], button, input:not([type=hidden]), select, textarea, [tabindex]:not([tabindex="-1"])'
).length"""

PULAR_CONTEUDO = re.compile(r"(pular|ir|saltar|avan[cç]ar).*(conte[uú]do|principal)|skip", re.I)
JANELA_ARMADILHA = 12
MAX_ELEMENTOS_EM_ARMADILHA = 3
MAX_EXEMPLOS = 5


def analisar_sequencia(paradas: list[dict | None], focaveis: int) -> dict[str, Any]:
    """Recebe o elemento focado após cada Tab (None = foco saiu para a página) e tira as conclusões."""
    focos = [p for p in paradas if p]
    primeiro = focos[0] if focos else None
    link_pular = bool(
        primeiro
        and primeiro["tag"] == "a"
        and (primeiro.get("href") or "").startswith("#")
        and PULAR_CONTEUDO.search(primeiro.get("texto") or "")
    )

    # Armadilha: muitas paradas seguidas presas em até 3 elementos, havendo bem mais focáveis na página
    armadilha = None
    for i in range(len(paradas) - JANELA_ARMADILHA + 1):
        janela = paradas[i : i + JANELA_ARMADILHA]
        if any(p is None for p in janela):
            continue
        distintos = {p["seletor"] for p in janela}
        if len(distintos) <= MAX_ELEMENTOS_EM_ARMADILHA and focaveis > len(distintos) + 2:
            armadilha = {"elementos": sorted(distintos), "a_partir_do_tab": i + 1}
            break

    vistos: set[str] = set()
    sem_indicador = []
    for p in focos:
        if p["seletor"] in vistos:
            continue
        vistos.add(p["seletor"])
        if p["visivel"] and not p["indicador"]:
            sem_indicador.append({"seletor": p["seletor"], "texto": p["texto"]})

    return {
        "tabs_pressionados": len(paradas),
        "elementos_alcancados": len(vistos),
        "elementos_focaveis_na_pagina": focaveis,
        "link_pular_conteudo": link_pular,
        "primeiro_foco": primeiro and {"seletor": primeiro["seletor"], "texto": primeiro["texto"]},
        "armadilha_de_foco": armadilha,
        "sem_indicador_aparente": len(sem_indicador),
        "exemplos_sem_indicador": sem_indicador[:MAX_EXEMPLOS],
    }


async def testar_teclado(page: Any, tabs: int) -> dict[str, Any]:
    await page.evaluate(
        "() => { window.scrollTo(0, 0); document.activeElement && document.activeElement.blur(); }"
    )
    focaveis = await page.evaluate(JS_FOCAVEIS)
    paradas: list[dict | None] = []
    # Focáveis + uma janela de armadilha: o bastante para atravessar a página e notar se o foco prende
    for _ in range(min(tabs, focaveis + JANELA_ARMADILHA + 5)):
        await page.keyboard.press("Tab")
        paradas.append(await page.evaluate(JS_FOCO))
    return analisar_sequencia(paradas, focaveis)
