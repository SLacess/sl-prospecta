"""Regras fixas do Auditor com IA (CONSTITUICAO §8.2), sem IA: problemas, nota, plugin × código, honestidade.

A IA escolhe e explica os achados; o que precisa ser reproduzível e honesto fica aqui:
- a nota de 0 a 100 é uma fórmula (a mesma auditoria dá sempre a mesma nota);
- a separação plugin × código vem da tabela revisada por humanos em packages/knowledge;
- nenhum texto gerado sai com promessa de conformidade total (§2.2).
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

# --- Problemas encontrados ---------------------------------------------------


@dataclass(frozen=True)
class Problema:
    """Uma chave por tipo de problema: regra do axe ou verificação própria (teclado:, responsivo:...)."""

    chave: str
    gravidade: str  # critico | grave | moderado | leve
    paginas: tuple[str, ...]
    ocorrencias: int
    descricao: str


# Gravidade das verificações próprias, alinhada ao impacto para quem usa teclado ou leitor de tela
GRAVIDADE_PROPRIA = {
    "teclado:armadilha_de_foco": "critico",
    "teclado:sem_indicador_de_foco": "grave",
    "teclado:sem_link_pular_conteudo": "moderado",
    "responsivo:rolagem_horizontal_320": "grave",
    "semantica:links_genericos": "moderado",
    "semantica:salto_de_titulo": "leve",
}
DESCRICAO_PROPRIA = {
    "teclado:armadilha_de_foco": "O foco do teclado fica preso num grupo de elementos.",
    "teclado:sem_indicador_de_foco": "Elementos recebem o foco do teclado sem indicação visual aparente.",
    "teclado:sem_link_pular_conteudo": "Não há link para pular direto ao conteúdo principal.",
    "responsivo:rolagem_horizontal_320": "Em 320 px de largura o conteúdo não cabe e exige rolagem lateral.",
    "semantica:links_genericos": "Links com texto genérico, como 'clique aqui' ou 'saiba mais'.",
    "semantica:salto_de_titulo": "Os títulos pulam níveis (ex.: de h1 direto para h3).",
}
ORDEM_GRAVIDADE = {"critico": 0, "grave": 1, "moderado": 2, "leve": 3}


def problemas_da_auditoria(paginas: list[dict[str, Any]]) -> list[Problema]:
    """Agrupa as páginas testadas em problemas únicos (a mesma regra em várias páginas conta uma vez)."""
    acumulado: dict[str, dict[str, Any]] = {}

    def somar(chave: str, gravidade: str, pagina: str, ocorrencias: int, descricao: str) -> None:
        item = acumulado.setdefault(
            chave, {"gravidade": gravidade, "paginas": [], "ocorrencias": 0, "descricao": descricao}
        )
        if ORDEM_GRAVIDADE[gravidade] < ORDEM_GRAVIDADE[item["gravidade"]]:
            item["gravidade"] = gravidade
        if pagina not in item["paginas"]:
            item["paginas"].append(pagina)
        item["ocorrencias"] += ocorrencias

    for p in paginas:
        if p.get("status") != "ok":
            continue
        url = p["url"]
        for v in p.get("axe", {}).get("violacoes", []):
            somar(v["regra"], v["gravidade"], url, v.get("ocorrencias", 1), v.get("descricao", ""))
        teclado = p.get("teclado", {})
        if teclado.get("armadilha_de_foco"):
            somar(
                "teclado:armadilha_de_foco", "critico", url, 1, DESCRICAO_PROPRIA["teclado:armadilha_de_foco"]
            )
        if teclado.get("sem_indicador_aparente", 0) > 0:
            chave = "teclado:sem_indicador_de_foco"
            somar(
                chave,
                GRAVIDADE_PROPRIA[chave],
                url,
                teclado["sem_indicador_aparente"],
                DESCRICAO_PROPRIA[chave],
            )
        if teclado.get("link_pular_conteudo") is False:
            chave = "teclado:sem_link_pular_conteudo"
            somar(chave, GRAVIDADE_PROPRIA[chave], url, 1, DESCRICAO_PROPRIA[chave])
        if p.get("responsivo_320", {}).get("rolagem_horizontal"):
            chave = "responsivo:rolagem_horizontal_320"
            somar(chave, GRAVIDADE_PROPRIA[chave], url, 1, DESCRICAO_PROPRIA[chave])
        semantica = p.get("semantica") or {}
        if semantica.get("links_genericos"):
            chave = "semantica:links_genericos"
            somar(
                chave,
                GRAVIDADE_PROPRIA[chave],
                url,
                len(semantica["links_genericos"]),
                DESCRICAO_PROPRIA[chave],
            )
        if semantica.get("saltos_de_titulo"):
            chave = "semantica:salto_de_titulo"
            somar(
                chave,
                GRAVIDADE_PROPRIA[chave],
                url,
                len(semantica["saltos_de_titulo"]),
                DESCRICAO_PROPRIA[chave],
            )

    problemas = [
        Problema(
            chave=k,
            gravidade=v["gravidade"],
            paginas=tuple(v["paginas"]),
            ocorrencias=v["ocorrencias"],
            descricao=v["descricao"],
        )
        for k, v in acumulado.items()
    ]
    return sorted(problemas, key=lambda pr: (ORDEM_GRAVIDADE[pr.gravidade], -len(pr.paginas), pr.chave))


# --- Nota 0–100 --------------------------------------------------------------

DESCONTO_POR_GRAVIDADE = {"critico": 12, "grave": 6, "moderado": 3, "leve": 1}
# Problemas que vários sites têm em todas as páginas pesam um pouco mais quando se repetem
DESCONTO_EXTRA_POR_PAGINA = 1
VERSAO_NOTA = "1.0"


def calcular_nota(problemas: list[Problema]) -> tuple[int, list[dict[str, Any]]]:
    """Parte de 100 e desconta por problema único. Devolve a nota e a explicação de cada desconto."""
    descontos = []
    for pr in problemas:
        valor = DESCONTO_POR_GRAVIDADE[pr.gravidade] + DESCONTO_EXTRA_POR_PAGINA * (len(pr.paginas) - 1)
        descontos.append({"problema": pr.chave, "gravidade": pr.gravidade, "pontos": valor})
    nota = max(0, min(100, 100 - sum(d["pontos"] for d in descontos)))
    return nota, descontos


# --- Plugin × código ---------------------------------------------------------


def _pasta_knowledge() -> Path:
    aqui = Path(__file__).resolve()
    for base in (aqui.parents[2], aqui.parents[3]):
        if (base / "packages" / "knowledge").is_dir():
            return base / "packages" / "knowledge"
    raise FileNotFoundError("packages/knowledge não encontrado")


@lru_cache
def tabela_plugin() -> dict[str, Any]:
    return json.loads((_pasta_knowledge() / "plugin-sinal-link.json").read_text(encoding="utf-8"))


def classificar(chave: str) -> tuple[str, str]:
    """(lado, rótulo). Problema fora da tabela vai para 'codigo': nunca prometemos o que o plugin não faz."""
    tabela = tabela_plugin()
    if chave in tabela["problemas"]:
        item = tabela["problemas"][chave]
        return item["lado"], item["rotulo"]
    for prefixo, item in tabela.get("prefixos", {}).items():
        if chave.startswith(prefixo):
            return item["lado"], item["rotulo"]
    return "codigo", chave


def separar_plugin_codigo(problemas: list[Problema]) -> tuple[list[str], list[str]]:
    plugin: list[str] = []
    codigo: list[str] = []
    for pr in problemas:
        lado, rotulo = classificar(pr.chave)
        destino = plugin if lado == "plugin_parcial" else codigo
        if rotulo not in destino:
            destino.append(rotulo)
    return plugin, codigo


# --- Honestidade técnica (§2.2) ----------------------------------------------

OBSERVACAO_HONESTIDADE = (
    "Teste automatizado com apoio de IA em até 5 páginas públicas. "
    "Ferramentas automáticas encontram só parte das barreiras de acessibilidade; "
    "o restante exige avaliação humana. "
    "Não substitui uma auditoria manual completa nem é parecer jurídico."
)

_PROIBIDAS = [
    r"100\s*%\s*acessivel",
    r"totalmente acessivel",
    r"completamente acessivel",
    r"plenamente acessivel",
    r"(conformidade|adequacao) (total|plena|completa|integral)",
    r"garant\w* (a |de )?(conformidade|adequacao|acessibilidade)",
    r"(elimina|resolve|corrige) (todas|todos) (as |os )?(barreiras|problemas)",
    r"livre de (multas|processos|riscos)",
]
_PADRAO_PROIBIDO = re.compile("|".join(_PROIBIDAS))


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def frases_proibidas(texto: str) -> list[str]:
    return [m.group(0) for m in _PADRAO_PROIBIDO.finditer(_normalizar(texto))]
