"""Agente Pesquisador (CONSTITUICAO §6 e §7.3, Etapa 1).

Duas funções: resolver o domínio oficial a partir do nome (busca na web) e montar o dossiê a partir
das páginas lidas. Devolve modelos validados ao orquestrador; nunca grava no banco.
"""

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from slp_workers.llm import ClienteIA, Consumo, RespostaBusca, extrair_json
from slp_workers.settings import WorkerConfig
from slp_workers.web.dominio import normalizar_dominio, pertence_ao_dominio
from slp_workers.web.fetcher import Pagina

AGENTE = "pesquisador"
MAX_CANDIDATOS = 3

# --- Saídas ------------------------------------------------------------------


class CandidatoDominio(BaseModel):
    dominio: str
    nome_oficial: str
    evidencia_url: str
    confianca: Literal["alta", "media", "baixa"]


class ResolucaoDominio(BaseModel):
    candidatos: list[CandidatoDominio]
    raciocinio_resumido: str


class Mencao(BaseModel):
    tema: Literal["inclusao", "diversidade", "pcd", "acessibilidade", "esg"]
    trecho: str = Field(description="Fragmento do texto da página que comprova a menção")
    url: str = Field(description="URL exata de uma das páginas recebidas")


class Sinal(BaseModel):
    tipo: Literal["vaga_pcd_ou_inclusao", "relatorio_esg", "pagina_acessibilidade", "app_ou_portal", "outro"]
    descricao: str
    url: str = Field(description="URL exata de uma das páginas recebidas")


class Localizacao(BaseModel):
    cidade: str | None
    uf: str | None = Field(description="Sigla do estado, ex.: SP")
    url: str | None = Field(description="URL exata da página onde a localização aparece")


class Dossie(BaseModel):
    """`dossie.json` (CONSTITUICAO §7.3). Esquema publicado em packages/schemas/dossie.schema.json."""

    nome_oficial: str
    setor: Literal["saude", "educacao", "utilities", "ecommerce", "financeiro", "outro"]
    subsetor: str | None
    descricao: str = Field(description="O que a empresa faz, em uma ou duas frases")
    missao: str | None
    produtos_servicos: list[str]
    publicos_atendidos: list[str]
    localizacao: Localizacao
    porte_indicios: str | None = Field(description="Só o que o site afirma, ex.: '12 unidades em SP'")
    mencoes_inclusao: list[Mencao]
    sinais: list[Sinal]
    lacunas: list[str]
    resumo_5_linhas: list[str]
    raciocinio_resumido: str


# --- Prompts -----------------------------------------------------------------


def _pasta_prompts() -> Path:
    aqui = Path(__file__).resolve()
    # /app/packages na imagem do worker; <repo>/packages ao rodar do código-fonte
    for base in (aqui.parents[2], aqui.parents[3]):
        if (base / "packages" / "prompts").is_dir():
            return base / "packages" / "prompts"
    raise FileNotFoundError("packages/prompts não encontrado")


@lru_cache
def carregar_prompt(nome: str) -> str:
    texto = (_pasta_prompts() / f"{nome}.md").read_text(encoding="utf-8")
    if texto.startswith("<!--"):
        texto = texto.split("-->", 1)[1]
    return texto.strip()


def hash_entrada(*partes: str) -> str:
    return hashlib.sha256("\n".join(partes).encode()).hexdigest()


# --- Resolução de domínio ----------------------------------------------------


async def resolver_dominio(
    ia: ClienteIA, config: WorkerConfig, nome: str
) -> tuple[ResolucaoDominio, RespostaBusca]:
    conteudo = f"Nome digitado pelo vendedor: {nome}"
    resposta = await ia.com_busca_web(
        modelo=config.model_analysis,
        sistema=carregar_prompt("researcher-dominio"),
        conteudo=conteudo,
        max_buscas=config.research_max_web_searches,
        effort="low",
        max_tokens=4000,
    )
    try:
        resolucao = ResolucaoDominio.model_validate(extrair_json(resposta.texto))
    except ValueError:
        resolucao = ResolucaoDominio(
            candidatos=[], raciocinio_resumido="A resposta da busca não trouxe candidatos."
        )
    return resolucao, resposta


def verificar_candidatos(resolucao: ResolucaoDominio, urls_consultadas: list[str]) -> list[CandidatoDominio]:
    """Mantém só domínios válidos que apareceram de fato nos resultados da busca (sem domínio inventado)."""
    hosts = {urlsplit(u).hostname for u in urls_consultadas}
    verificados: list[CandidatoDominio] = []
    for c in resolucao.candidatos:
        dominio = normalizar_dominio(c.dominio)
        if not dominio or any(v.dominio == dominio for v in verificados):
            continue
        if not any(pertence_ao_dominio(h, dominio) for h in hosts):
            continue
        verificados.append(c.model_copy(update={"dominio": dominio}))
    return verificados[:MAX_CANDIDATOS]


# --- Dossiê ------------------------------------------------------------------


def _conteudo_dossie(dominio: str, nome_informado: str, paginas: list[Pagina]) -> str:
    blocos = []
    for p in paginas:
        cabecalho = f"Título: {p.titulo}\nDescrição: {p.descricao}\n" if (p.titulo or p.descricao) else ""
        blocos.append(f'<pagina url="{p.url}">\n{cabecalho}{p.texto}\n</pagina>')
    return f"Empresa informada pelo vendedor: {nome_informado}\nDomínio oficial: {dominio}\n\n" + "\n\n".join(
        blocos
    )


async def montar_dossie(
    ia: ClienteIA, config: WorkerConfig, dominio: str, nome_informado: str, paginas: list[Pagina]
) -> tuple[Dossie, Consumo, str]:
    conteudo = _conteudo_dossie(dominio, nome_informado, paginas)
    sistema = carregar_prompt("researcher")
    dossie, consumo = await ia.estruturado(
        modelo=config.model_analysis,
        sistema=sistema,
        conteudo=conteudo,
        formato=Dossie,
        effort="medium",
        max_tokens=16000,
    )
    return dossie, consumo, hash_entrada(sistema, conteudo)


def _canonica(url: str | None) -> str:
    if not url:
        return ""
    partes = urlsplit(url.strip())
    return f"{(partes.hostname or '').lower()}{partes.path.rstrip('/') or '/'}"


def validar_fontes(dossie: Dossie, urls_lidas: list[str]) -> tuple[Dossie, int]:
    """Descarta menções, sinais e localização que citam página não lida (CONSTITUICAO §15.3)."""
    lidas = {_canonica(u) for u in urls_lidas}
    mencoes = [m for m in dossie.mencoes_inclusao if _canonica(m.url) in lidas]
    sinais = [s for s in dossie.sinais if _canonica(s.url) in lidas]
    localizacao = dossie.localizacao
    removidos = (len(dossie.mencoes_inclusao) - len(mencoes)) + (len(dossie.sinais) - len(sinais))
    if localizacao.url and _canonica(localizacao.url) not in lidas:
        localizacao = Localizacao(cidade=None, uf=None, url=None)
        removidos += 1
    lacunas = list(dossie.lacunas)
    if removidos:
        lacunas.append(f"{removidos} informação(ões) descartada(s) por citar página que não foi lida")
    validado = dossie.model_copy(
        update={
            "mencoes_inclusao": mencoes,
            "sinais": sinais,
            "localizacao": localizacao,
            "lacunas": lacunas,
            "resumo_5_linhas": [linha.strip() for linha in dossie.resumo_5_linhas if linha.strip()][:5],
        }
    )
    return validado, removidos
