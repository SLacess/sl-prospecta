"""Camada automática de regras: axe-core via Playwright (CONSTITUICAO §8.1)."""

from functools import lru_cache
from pathlib import Path
from typing import Any

TAGS_WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]

# Nomes do §8.2 para as gravidades do axe
GRAVIDADE = {"critical": "critico", "serious": "grave", "moderate": "moderado", "minor": "leve"}
MAX_EXEMPLOS = 3
MAX_HTML = 300

JS_RODAR_AXE = """async (tags) => {
  const r = await window.axe.run(document, {
    runOnly: { type: "tag", values: tags },
    resultTypes: ["violations", "incomplete"],
  });
  return {
    violations: r.violations.map((v) => ({
      id: v.id, impact: v.impact, help: v.help, helpUrl: v.helpUrl, tags: v.tags,
      nodes: v.nodes.map((n) => ({ target: n.target, html: n.html })),
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
