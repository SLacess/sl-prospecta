"""Detecção de plugin/overlay de acessibilidade já instalado (CONSTITUICAO §8.1, última camada).

Pela assinatura dos scripts carregados e de variáveis globais conhecidas. Só registra o que
encontrou; não avalia a qualidade do plugin.
"""

import re

ASSINATURAS: list[tuple[str, re.Pattern[str]]] = [
    ("UserWay", re.compile(r"userway\.org|UserWayWidget", re.I)),
    ("accessiBe", re.compile(r"acsbapp\.com|accessibe\.com|acsbJS", re.I)),
    ("EqualWeb", re.compile(r"equalweb\.com|nagishli|INDmenu", re.I)),
    ("Hand Talk", re.compile(r"handtalk", re.I)),
    ("VLibras", re.compile(r"vlibras\.gov\.br|vw-plugin-wrapper|VLibras\.Widget", re.I)),
    ("AudioEye", re.compile(r"audioeye\.com", re.I)),
    ("Recite Me", re.compile(r"reciteme\.com", re.I)),
    ("Equally AI", re.compile(r"equally\.ai", re.I)),
    ("Rybená", re.compile(r"rybena", re.I)),
    ("Sinal Link", re.compile(r"sinallink", re.I)),
]

# Coletado na página: srcs de scripts, ids/classes de widgets e nomes de variáveis globais
JS_SINAIS = """() => {
  const scripts = [...document.scripts].map((s) => s.src || "").filter(Boolean);
  const widgets = [...document.querySelectorAll("[id],[class]")]
    .slice(0, 3000)
    .map((el) => `${el.id || ""} ${typeof el.className === "string" ? el.className : ""}`)
    .filter((t) =>
      /userway|acsb|vlibras|vw-plugin|handtalk|equalweb|INDmenu|reciteme|rybena|sinallink/i.test(t));
  const globais = ["UserWayWidget", "acsbJS", "VLibras", "INDmenu", "nagishli"]
    .filter((nome) => typeof window[nome] !== "undefined");
  return [...scripts, ...widgets, ...globais].join("\\n");
}"""


def detectar_plugins(sinais: str) -> list[str]:
    return [nome for nome, padrao in ASSINATURAS if padrao.search(sinais)]
