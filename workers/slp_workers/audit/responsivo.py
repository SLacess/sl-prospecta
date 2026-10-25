"""Teste em 320 px de largura (WCAG 1.4.10 Reflow, CONSTITUICAO §8.1).

320 px CSS equivalem a 400% de zoom numa tela de 1280 px: o conteúdo deve caber sem rolagem horizontal.
"""

from typing import Any

LARGURA = 320
ALTURA = 640

JS_ESTOURO = """() => {
  const doc = document.documentElement;
  const largura = doc.clientWidth;
  const estouram = [];
  for (const el of document.body ? document.body.querySelectorAll("*") : []) {
    if (estouram.length >= 5) break;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.right <= largura + 2) continue;
    const css = getComputedStyle(el);
    if (css.position === "fixed" || css.visibility === "hidden") continue;
    // Só o elemento mais interno que estoura (o filho explica o pai)
    if ([...el.children].some((c) => c.getBoundingClientRect().right > largura + 2)) continue;
    const classes = typeof el.className === "string" ? el.className.trim().split(/\\s+/).filter(Boolean) : [];
    estouram.push({
      seletor: el.tagName.toLowerCase() + (el.id ? `#${el.id}` : "") +
        (classes.length ? "." + classes.slice(0, 2).join(".") : ""),
      largura_px: Math.round(r.width),
    });
  }
  return { largura_pagina: doc.scrollWidth, largura_tela: largura, estouram };
}"""


async def testar_320(page: Any) -> tuple[dict[str, Any], bytes]:
    original = page.viewport_size
    await page.set_viewport_size({"width": LARGURA, "height": ALTURA})
    try:
        await page.wait_for_timeout(600)  # dá tempo para os media queries e o layout
        medida = await page.evaluate(JS_ESTOURO)
        print_320 = await page.screenshot(type="png")
    finally:
        if original:
            await page.set_viewport_size(original)
    medida["rolagem_horizontal"] = medida["largura_pagina"] > medida["largura_tela"] + 2
    return medida, print_320
