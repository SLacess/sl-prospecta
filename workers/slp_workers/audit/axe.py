"""Camada automática de regras: axe-core via Playwright (CONSTITUICAO §8.1)."""

from functools import lru_cache
from pathlib import Path
from typing import Any

TAGS_WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

# Nomes do §8.2 para as gravidades do axe
GRAVIDADE = {"critical": "critico", "serious": "grave", "moderate": "moderado", "minor": "leve"}
MAX_EXEMPLOS = 3
MAX_HTML = 300

# Viewport do print desktop (engine.py): a caixa só vale se o elemento aparece nele
LARGURA_PRINT, ALTURA_PRINT = 1366, 768

JS_RODAR_AXE = """async (tags) => {
  window.scrollTo(0, 0);
  const r = await window.axe.run(document, {
    runOnly: { type: "tag", values: tags },
    resultTypes: ["violations", "incomplete"],
    elementRef: true,
  });
  // Posição do primeiro exemplo de cada problema, na mesma tela do print desktop (caixa no relatório)
  const caixa = (el) => {
    if (!el || !el.getBoundingClientRect) return null;
    const b = el.getBoundingClientRect();
    if (b.width < 2 || b.height < 2) return null;
    const r = Math.round;
    return { x: r(b.left), y: r(b.top), largura: r(b.width), altura: r(b.height) };
  };
  return {
    violations: r.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, tags: v.tags,
      nodes: v.nodes.map((n, i) => ({
        target: n.target, html: n.html, caixa: i === 0 ? caixa(n.element) : null,
      })),
    })),
    incompletos: r.incomplete.length,
    versao: r.testEngine.version,
  };
}"""


@lru_cache
def codigo_axe(caminho: str) -> str:
    arquivo = Path(caminho)
    if not arquivo.exists():
        raise FileNotFoundError(f"axe-core não encontrado em {caminho} (rode scripts/baixar_axe.py)")
    return arquivo.read_text(encoding="utf-8")


def caixa_no_print(caixa: dict[str, int] | None) -> dict[str, int] | None:
    """Mantém só caixas que aparecem no print desktop, recortadas aos limites da imagem."""
    if not caixa:
        return None
    x, y = max(0, caixa["x"]), max(0, caixa["y"])
    direita = min(LARGURA_PRINT, caixa["x"] + caixa["largura"])
    baixo = min(ALTURA_PRINT, caixa["y"] + caixa["altura"])
    if direita - x < 2 or baixo - y < 2:
        return None
    return {"x": x, "y": y, "largura": direita - x, "altura": baixo - y}


def resumir(bruto: dict[str, Any]) -> dict[str, Any]:
    """Resultado compacto por página: regra, gravidade, ocorrências e até 3 exemplos de HTML."""
    violacoes = []
    for v in bruto["violations"]:
        violacoes.append(
            {
                "regra": v["id"],
                "gravidade": GRAVIDADE.get(v.get("impact") or "", "leve"),
                "descricao": v["help"],
                "ajuda_url": v["helpUrl"],
                "criterios_wcag": [t for t in v["tags"] if t.startswith("wcag") and t[4:].isdigit()],
                "ocorrencias": len(v["nodes"]),
                "exemplos": [
                    {"alvo": " ".join(str(t) for t in n["target"]), "html": n["html"][:MAX_HTML]}
                    for n in v["nodes"][:MAX_EXEMPLOS]
                ],
                "caixa": caixa_no_print(v["nodes"][0].get("caixa") if v["nodes"] else None),
            }
        )
    return {
        "versao_axe": bruto.get("versao"),
        "violacoes": violacoes,
        "incompletos": bruto.get("incompletos", 0),
    }


async def rodar_axe(page: Any, caminho_axe: str) -> dict[str, Any]:
    # evaluate roda pelo protocolo do navegador: a política de segurança (CSP) do site não bloqueia
    await page.evaluate(codigo_axe(caminho_axe) + "\n;true")
    return resumir(await page.evaluate(JS_RODAR_AXE, TAGS_WCAG))
