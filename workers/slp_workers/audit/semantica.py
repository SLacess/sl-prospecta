"""Camada semântica sem IA (CONSTITUICAO §8.1): links genéricos e saltos na hierarquia de títulos.

Links "clique aqui" e "saiba mais" não dizem nada a quem navega pela lista de links do leitor de tela
(WCAG 2.4.4); títulos que pulam níveis bagunçam a navegação por títulos (WCAG 1.3.1).
"""

from typing import Any

GENERICOS = [
    "clique aqui",
    "clique",
    "aqui",
    "saiba mais",
    "leia mais",
    "veja mais",
    "ver mais",
    "mais",
    "acesse",
    "acesse aqui",
    "confira",
    "veja",
    "link",
    "click here",
    "read more",
    "more",
]

JS_SEMANTICA = """(genericos) => {
  const normalizar = (t) => (t || "").normalize("NFD").replace(/[\\u0300-\\u036f]/g, "")
    .toLowerCase().replace(/[^a-z0-9 ]/g, " ").replace(/\\s+/g, " ").trim();
  const alvo = new Set(genericos.map(normalizar));
  const links = [];
  for (const a of document.querySelectorAll("a[href]")) {
    const r = a.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    const nome = a.getAttribute("aria-label") || a.innerText || "";
    if (alvo.has(normalizar(nome)) && !a.getAttribute("aria-describedby")) {
      if (links.length < 10) links.push({ texto: nome.trim().slice(0, 40), href: a.getAttribute("href") });
    }
  }
  const saltos = [];
  let anterior = 0;
  for (const h of document.querySelectorAll("h1, h2, h3, h4, h5, h6")) {
    const nivel = Number(h.tagName[1]);
    if (anterior && nivel > anterior + 1 && saltos.length < 10) {
      saltos.push({ de: `h${anterior}`, para: `h${nivel}`, texto: (h.innerText || "").trim().slice(0, 60) });
    }
    anterior = nivel;
  }
  return { links_genericos: links, saltos_de_titulo: saltos };
}"""


async def analisar_semantica(page: Any) -> dict[str, Any]:
    return await page.evaluate(JS_SEMANTICA, GENERICOS)
