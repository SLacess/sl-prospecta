"""Mini-relatório de acessibilidade (CONSTITUICAO §8.3): uma página A4 em PDF acessível e uma versão web.

Sem IA: usa a análise já gravada pela Tarefa 4 (nota, achados, plugin × código), as ações recomendadas
revisadas por humanos (packages/knowledge/acoes-recomendadas.json) e a média do setor, que só aparece com
base suficiente. O PDF sai com tags (PDF/UA-1), idioma pt-BR, título e texto alternativo em cada imagem.
"""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from slp_workers.audit.axe import ALTURA_PRINT, LARGURA_PRINT
from slp_workers.audit.regras import Problema, frases_proibidas, problemas_da_auditoria

MIN_SITES_BENCHMARK = 5
ROTULO_SETOR = {
    "saude": "saúde",
    "educacao": "educação",
    "utilities": "utilities e concessões",
    "ecommerce": "e-commerce e varejo",
    "financeiro": "serviços financeiros",
    "outro": "outros setores",
}
MESES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def _raiz() -> Path:
    aqui = Path(__file__).resolve()
    for base in (aqui.parents[2], aqui.parents[3]):
        if (base / "templates" / "relatorio").is_dir():
            return base
    raise FileNotFoundError("templates/relatorio não encontrado")


@lru_cache
def acoes_recomendadas() -> dict[str, Any]:
    return json.loads(
        (_raiz() / "packages" / "knowledge" / "acoes-recomendadas.json").read_text(encoding="utf-8")
    )


def _data_uri(dados: bytes, tipo: str) -> str:
    return f"data:{tipo};base64,{base64.b64encode(dados).decode()}"


@lru_cache
def _recursos_marca() -> dict[str, str]:
    marca = _raiz() / "templates" / "relatorio" / "marca"
    fontes = []
    for peso in (400, 700):
        uri = _data_uri((marca / f"dm-sans-latin-{peso}.woff").read_bytes(), "font/woff")
        fontes.append(
            f'@font-face {{ font-family: "DM Sans"; font-weight: {peso}; src: url("{uri}") format("woff"); }}'
        )
    return {
        "logo": _data_uri((marca / "logo-sinal-link.png").read_bytes(), "image/png"),
        "fontes_css": "\n".join(fontes),
        "marca_css": (_raiz() / "templates" / "relatorio" / "marca.css").read_text(encoding="utf-8"),
    }


@lru_cache
def _ambiente() -> Environment:
    return Environment(
        loader=FileSystemLoader(_raiz() / "templates" / "relatorio"), autoescape=select_autoescape(["html"])
    )


# --- Conteúdo ----------------------------------------------------------------


def faixa_da_nota(nota: int) -> str:
    if nota >= 80:
        return "Boa base, com ajustes pontuais"
    if nota >= 50:
        return "Barreiras que merecem atenção"
    return "Barreiras importantes"


def _acao_do_problema(chave: str) -> dict[str, Any] | None:
    tabela = acoes_recomendadas()
    if chave in tabela["por_problema"]:
        return tabela["por_problema"][chave]
    for prefixo, acao in tabela["por_prefixo"].items():
        if chave.startswith(prefixo):
            return acao
    return None


def escolher_acoes(problemas: list[Problema], plugin_parcial: list[str]) -> list[dict[str, Any]]:
    """Três ações: a 1ª gratuita (§8.3), a 2ª para o problema mais grave, a 3ª da Sinal Link."""
    tabela = acoes_recomendadas()
    acoes: list[dict[str, Any]] = []

    gratuita = next(
        (a for pr in problemas if (a := _acao_do_problema(pr.chave)) and a["gratuita"]),
        tabela["gratuita_padrao"],
    )
    acoes.append(gratuita)
    for pr in problemas:
        acao = _acao_do_problema(pr.chave)
        if acao and acao["acao"] != gratuita["acao"]:
            acoes.append(acao)
            break
    if len(acoes) < 2:
        acoes.append(tabela["sinal_link"]["avaliacao_humana"])
    acoes.append(tabela["sinal_link"]["plugin" if plugin_parcial else "avaliacao_humana"])
    if acoes[2]["acao"] == acoes[1]["acao"]:
        acoes[2] = tabela["sinal_link"]["plugin"]
    return acoes[:3]


def comparacao_setor(setor: str | None, media: float | None, quantidade: int) -> str:
    rotulo = ROTULO_SETOR.get(setor or "", "este setor")
    if media is None or quantidade < MIN_SITES_BENCHMARK:
        return (
            f"Ainda não há base suficiente para comparar com a média de {rotulo}: comparamos a partir de "
            f"{MIN_SITES_BENCHMARK} sites analisados no setor."
        )
    return f"Média de {rotulo} na base da Sinal Link: {round(media)} de 100 ({quantidade} sites analisados)."


def _caixa_percentual(caixa: dict[str, int] | None) -> dict[str, float] | None:
    if not caixa:
        return None
    return {
        "left": round(caixa["x"] / LARGURA_PRINT * 100, 2),
        "top": round(caixa["y"] / ALTURA_PRINT * 100, 2),
        "width": round(caixa["largura"] / LARGURA_PRINT * 100, 2),
        "height": round(caixa["altura"] / ALTURA_PRINT * 100, 2),
    }


def _caixa_do_problema(paginas: list[dict[str, Any]], url: str, problema: str) -> dict[str, int] | None:
    for p in paginas:
        if p.get("url") == url and p.get("status") == "ok":
            for v in p.get("axe", {}).get("violacoes", []):
                if v["regra"] == problema:
                    return v.get("caixa")
    return None


def _data_extenso(momento: datetime) -> str:
    local = momento.astimezone(ZoneInfo("America/Sao_Paulo"))
    return f"{local.day} de {MESES[local.month - 1]} de {local.year}"


@dataclass
class DadosRelatorio:
    nome: str
    dominio: str
    setor: str | None
    nota: int
    analise: dict[str, Any]  # JSON do §8.2 (auditorias.achados_json)
    paginas: list[dict[str, Any]]  # resultado bruto do Auditor técnico
    prints: dict[str, bytes]  # url s3 do print desktop -> PNG
    media_setor: float | None
    sites_no_setor: int
    gerado_em: datetime


def montar_contexto(d: DadosRelatorio) -> dict[str, Any]:
    problemas = problemas_da_auditoria(d.paginas)
    achados = []
    for i, a in enumerate(d.analise.get("top3_para_leigos", []), start=1):
        url_print = (a.get("evidencia") or {}).get("print")
        png = d.prints.get(url_print) if url_print else None
        caixa = _caixa_percentual(
            _caixa_do_problema(d.paginas, a.get("pagina_url", ""), a.get("problema", ""))
        )
        achados.append(
            {
                "numero": i,
                "titulo": a["titulo"],
                "impacto_humano": a["impacto_humano"],
                "criterio_wcag": a["criterio_wcag"],
                "pagina": a["pagina"],
                "print": _data_uri(png, "image/png") if png else None,
                "caixa": caixa if png else None,
                "alt_print": (
                    f"Print da página {a['pagina']} de {d.dominio}"
                    + (f", com o problema {i} destacado por uma caixa numerada." if caixa else ".")
                ),
            }
        )
    grupos: list[str] = []
    for a in d.analise.get("top3_para_leigos", []):
        for g in a.get("quem_e_afetado", []):
            if g not in grupos:
                grupos.append(g)
    totais = d.analise.get("totais") or {}
    return {
        **_recursos_marca(),
        "empresa": {"nome": d.nome, "dominio": d.dominio},
        "data": _data_extenso(d.gerado_em),
        "data_iso": d.gerado_em.astimezone(UTC).date().isoformat(),
        "nota": d.nota,
        "faixa": faixa_da_nota(d.nota),
        "comparacao": comparacao_setor(d.setor, d.media_setor, d.sites_no_setor),
        "paginas_auditadas": d.analise.get("paginas_auditadas", 0),
        "totais": {k: totais.get(k, 0) for k in ("critico", "grave", "moderado", "leve")},
        "achados": achados,
        "quem_e_afetado": grupos or ["pessoas com deficiência e pessoas idosas"],
        "acoes": escolher_acoes(problemas, d.analise.get("plugin_resolve_parcialmente", [])),
        "observacao": d.analise.get("observacao_honestidade", ""),
        "versao_nota": d.analise.get("versao_nota", "1.0"),
    }


class RelatorioDesonesto(ValueError):
    """O texto final tem promessa proibida pelo §2.2 (não deveria acontecer: a análise já filtra)."""


def gerar_html(d: DadosRelatorio) -> str:
    html = _ambiente().get_template("relatorio.html").render(**montar_contexto(d))
    proibidas = frases_proibidas(html)
    if proibidas:
        raise RelatorioDesonesto(", ".join(proibidas))
    return html


def gerar_pdf(html: str) -> bytes:
    """PDF/UA-1 (com tags) a partir do mesmo HTML da versão web. WeasyPrint precisa do Pango no sistema."""
    from weasyprint import HTML

    return HTML(string=html, base_url=str(_raiz() / "templates" / "relatorio")).write_pdf(
        pdf_variant="pdf/ua-1"
    )
