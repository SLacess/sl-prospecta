"""Agente Auditor com IA (CONSTITUICAO §6, §8.1 e §8.2).

Recebe os problemas encontrados pelo Auditor técnico e até 3 prints, escolhe e explica os 3 achados para
leigos e aponta indícios visuais. A nota, a separação plugin × código e a observação de honestidade vêm
de regras fixas (`slp_workers.audit.regras`). Devolve dados validados ao orquestrador; não grava no banco.
"""

import base64
import json
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.audit.regras import (
    OBSERVACAO_HONESTIDADE,
    VERSAO_NOTA,
    Problema,
    calcular_nota,
    frases_proibidas,
    problemas_da_auditoria,
    separar_plugin_codigo,
)
from slp_workers.llm import ClienteIA, Consumo, ErroIA
from slp_workers.settings import WorkerConfig

AGENTE = "auditor"
MAX_ACHADOS = 3
MAX_IMAGENS = 3
MAX_EXEMPLOS_POR_PROBLEMA = 2

GrupoAfetado = Literal[
    "pessoas cegas",
    "pessoas com baixa visão",
    "pessoas daltônicas",
    "pessoas surdas",
    "pessoas com deficiência motora",
    "pessoas idosas",
    "pessoas neurodivergentes",
]


class AchadoIA(BaseModel):
    problema: str = Field(description="Chave do problema, copiada da lista recebida")
    pagina: str = Field(description="URL de uma das páginas em que o problema foi encontrado")
    titulo: str
    impacto_humano: str
    quem_e_afetado: list[GrupoAfetado]
    criterio_wcag: str
    trecho_html: str | None = Field(description="Exemplo de HTML recebido, copiado sem alteração")


class IndicioVisual(BaseModel):
    tipo: Literal[
        "texto_em_imagem", "informacao_so_por_cor", "captcha_visual", "video_sem_legenda_aparente", "outro"
    ]
    descricao: str
    pagina: str


class AnaliseIA(BaseModel):
    top3_para_leigos: list[AchadoIA]
    indicios_visuais: list[IndicioVisual]
    raciocinio_resumido: str


class Evidencia(BaseModel):
    print: str | None
    trecho_html: str | None


class AchadoParaLeigos(BaseModel):
    titulo: str
    impacto_humano: str
    quem_e_afetado: list[str]
    criterio_wcag: str
    evidencia: Evidencia
    pagina: str
    pagina_url: str
    problema: str


class Totais(BaseModel):
    critico: int
    grave: int
    moderado: int
    leve: int


class Desconto(BaseModel):
    problema: str
    gravidade: str
    pontos: int


class ResultadoAuditoriaIA(BaseModel):
    """JSON do §8.2 gravado em auditorias.achados_json. Esquema em packages/schemas/auditoria.schema.json."""

    nota_geral: int = Field(ge=0, le=100)
    paginas_auditadas: int
    totais: Totais
    top3_para_leigos: list[AchadoParaLeigos]
    plugin_resolve_parcialmente: list[str]
    exige_ajuste_no_codigo: list[str]
    indicios_visuais: list[IndicioVisual]
    observacao_honestidade: str
    descontos_nota: list[Desconto]
    versao_nota: str
    raciocinio_resumido: str


class ErroHonestidade(ErroIA):
    """O texto gerado prometeu mais do que a auditoria permite (CONSTITUICAO §2.2)."""


# --- Entrada para o modelo ---------------------------------------------------


def _exemplos(paginas: list[dict[str, Any]], regra: str) -> list[dict[str, str]]:
    exemplos = []
    for p in paginas:
        if p.get("status") != "ok":
            continue
        for v in p.get("axe", {}).get("violacoes", []):
            if v["regra"] == regra:
                for e in v.get("exemplos", [])[:MAX_EXEMPLOS_POR_PROBLEMA]:
                    exemplos.append({"pagina": p["url"], "html": e["html"]})
    return exemplos[:MAX_EXEMPLOS_POR_PROBLEMA]


def _criterios(paginas: list[dict[str, Any]], regra: str) -> list[str]:
    for p in paginas:
        for v in p.get("axe", {}).get("violacoes", []) if p.get("status") == "ok" else []:
            if v["regra"] == regra:
                return v.get("criterios_wcag", [])
    return []


def montar_conteudo(
    nome: str,
    setor: str | None,
    paginas: list[dict[str, Any]],
    problemas: list[Problema],
    prints: list[tuple[str, bytes]],
) -> list[dict[str, Any]]:
    lista = [
        {
            "problema": pr.chave,
            "gravidade": pr.gravidade,
            "descricao": pr.descricao,
            "paginas": list(pr.paginas),
            "ocorrencias": pr.ocorrencias,
            "criterios_wcag": _criterios(paginas, pr.chave),
            "exemplos_html": _exemplos(paginas, pr.chave),
        }
        for pr in problemas
    ]
    texto = (
        f"Organização: {nome}" + (f" (setor: {setor})" if setor else "") + "\n"
        f"Páginas testadas: {', '.join(p['url'] for p in paginas if p.get('status') == 'ok')}\n\n"
        "Problemas encontrados pelos testes automáticos (do mais grave ao mais leve):\n"
        f"<problemas>\n{json.dumps(lista, ensure_ascii=False, indent=1)}\n</problemas>"
    )
    blocos: list[dict[str, Any]] = []
    for url, png in prints[:MAX_IMAGENS]:
        blocos.append({"type": "text", "text": f"Print da página {url} (desktop):"})
        blocos.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(png).decode(),
                },
            }
        )
    blocos.append({"type": "text", "text": texto})
    return blocos


# --- Validação ---------------------------------------------------------------


def _mesma_pagina(a: str, b: str) -> bool:
    pa, pb = urlsplit(a), urlsplit(b)
    return (pa.hostname or "").lower() == (pb.hostname or "").lower() and (pa.path.rstrip("/") or "/") == (
        pb.path.rstrip("/") or "/"
    )


def validar_analise(
    analise: AnaliseIA, problemas: list[Problema], paginas: list[dict[str, Any]]
) -> tuple[AnaliseIA, int]:
    """Descarta achado com problema ou página inexistentes; apaga trecho de HTML que não é exemplo real."""
    por_chave = {pr.chave: pr for pr in problemas}
    validos: list[AchadoIA] = []
    descartados = 0
    for a in analise.top3_para_leigos:
        pr = por_chave.get(a.problema)
        if pr is None or any(v.problema == a.problema for v in validos):
            descartados += 1
            continue
        pagina = next((u for u in pr.paginas if _mesma_pagina(u, a.pagina)), None)
        if pagina is None:
            descartados += 1
            continue
        reais = {
            e["html"].strip()
            for p in paginas
            if p.get("status") == "ok"
            for v in p.get("axe", {}).get("violacoes", [])
            if v["regra"] == a.problema
            for e in v.get("exemplos", [])
        }
        trecho = a.trecho_html if a.trecho_html and a.trecho_html.strip() in reais else None
        validos.append(a.model_copy(update={"pagina": pagina, "trecho_html": trecho}))
        if len(validos) == MAX_ACHADOS:
            break
    urls_testadas = [p["url"] for p in paginas if p.get("status") == "ok"]
    indicios = [i for i in analise.indicios_visuais if any(_mesma_pagina(u, i.pagina) for u in urls_testadas)]
    return analise.model_copy(update={"top3_para_leigos": validos, "indicios_visuais": indicios}), descartados


def checar_honestidade(analise: AnaliseIA) -> None:
    textos = [analise.raciocinio_resumido]
    for a in analise.top3_para_leigos:
        textos += [a.titulo, a.impacto_humano]
    textos += [i.descricao for i in analise.indicios_visuais]
    proibidas = sorted({f for t in textos for f in frases_proibidas(t)})
    if proibidas:
        raise ErroHonestidade(f"texto com promessa proibida pelo §2.2: {', '.join(proibidas)}")


# --- Resultado final (§8.2) --------------------------------------------------


def montar_resultado(
    analise: AnaliseIA, problemas: list[Problema], paginas: list[dict[str, Any]], totais: dict[str, Any]
) -> tuple[int, dict[str, Any]]:
    nota, descontos = calcular_nota(problemas)
    plugin, codigo = separar_plugin_codigo(problemas)
    prints = {p["url"]: (p.get("prints") or {}).get("desktop") for p in paginas if p.get("status") == "ok"}
    top3 = [
        AchadoParaLeigos(
            titulo=a.titulo,
            impacto_humano=a.impacto_humano,
            quem_e_afetado=list(a.quem_e_afetado),
            criterio_wcag=a.criterio_wcag,
            evidencia=Evidencia(print=prints.get(a.pagina), trecho_html=a.trecho_html),
            pagina=urlsplit(a.pagina).path or "/",
            pagina_url=a.pagina,
            problema=a.problema,
        )
        for a in analise.top3_para_leigos
    ]
    resultado = ResultadoAuditoriaIA(
        nota_geral=nota,
        paginas_auditadas=totais.get("paginas_auditadas", len(prints)),
        totais=Totais(**{k: totais.get(k, 0) for k in ("critico", "grave", "moderado", "leve")}),
        top3_para_leigos=top3,
        plugin_resolve_parcialmente=plugin,
        exige_ajuste_no_codigo=codigo,
        indicios_visuais=analise.indicios_visuais,
        observacao_honestidade=OBSERVACAO_HONESTIDADE,
        descontos_nota=[Desconto(**d) for d in descontos],
        versao_nota=VERSAO_NOTA,
        raciocinio_resumido=analise.raciocinio_resumido,
    )
    return nota, resultado.model_dump()


async def analisar(
    ia: ClienteIA,
    config: WorkerConfig,
    nome: str,
    setor: str | None,
    paginas: list[dict[str, Any]],
    prints: list[tuple[str, bytes]],
) -> tuple[AnaliseIA, list[Problema], Consumo, str, int]:
    """Chama o modelo (com uma nova tentativa se o texto violar o §2.2) e valida a saída."""
    problemas = problemas_da_auditoria(paginas)
    conteudo = montar_conteudo(nome, setor, paginas, problemas, prints)
    sistema = carregar_prompt("auditor")
    entrada_hash = hash_entrada(sistema, json.dumps([b.get("text", "[imagem]") for b in conteudo]))

    gasto = Consumo(modelo=config.model_analysis)
    for tentativa in range(2):
        aviso = (
            ""
            if tentativa == 0
            else "\n\nATENÇÃO: a resposta anterior prometeu acessibilidade total ou conformidade. "
            "Reescreva sem nenhuma promessa desse tipo."
        )
        analise, consumo = await ia.estruturado(
            modelo=config.model_analysis,
            sistema=sistema + aviso,
            conteudo=conteudo,
            formato=AnaliseIA,
            effort="medium",
            max_tokens=16000,
        )
        gasto = gasto.somar(consumo)
        validada, descartados = validar_analise(analise, problemas, paginas)
        try:
            checar_honestidade(validada)
            if problemas and not validada.top3_para_leigos:
                raise ErroIA("nenhum achado apontou um problema e uma página reais da auditoria")
        except ErroIA as exc:
            if tentativa == 1:
                exc.consumo = gasto
                raise
            continue
        return validada, problemas, gasto, entrada_hash, descartados
    raise AssertionError("inalcançável")
