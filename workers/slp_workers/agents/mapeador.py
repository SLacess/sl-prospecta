"""Mapeador de decisores (CONSTITUICAO §6 e §7.3, Etapa 4).

Duas fontes de candidatos: a busca de pessoas do Apollo (sem crédito) e, quando ela não cobre as áreas, a
busca web do Claude em fontes públicas (site da empresa, imprensa, relatórios). O LinkedIn nunca é fonte:
um link de perfil só é guardado se apareceu nos resultados da busca (CLAUDE.md, regra 7).

O Haiku escolhe até 3 pessoas, uma por área (regra de multithreading). As saídas do modelo são validadas
aqui antes de o orquestrador gastar créditos: só vale quem está na lista de candidatos ou na busca.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.llm import ClienteIA, Consumo, RespostaBusca, extrair_json
from slp_workers.settings import WorkerConfig
from slp_workers.web.apollo import PessoaBusca

Area = Literal["TI", "RH", "D&I", "Marketing", "ESG", "Compliance"]
AREAS: tuple[str, ...] = ("TI", "RH", "D&I", "Marketing", "ESG", "Compliance")
PRIORIDADE_PADRAO = ["TI", "Marketing", "RH", "D&I", "ESG", "Compliance"]
# Padrão da migração 0005 (`config.decisores`); vale se a chave sumir da `config`
TITULOS_PADRAO: dict[str, list[str]] = {
    "TI": ["CTO", "CIO", "Diretor de TI", "Gerente de TI", "Head de Tecnologia", "Diretor de Tecnologia"],
    "RH": [
        "CHRO",
        "Diretor de RH",
        "Gerente de Recursos Humanos",
        "Head de Pessoas",
        "Diretor de Gente e Gestão",
    ],
    "D&I": ["Diversidade e Inclusão", "Diversity and Inclusion", "Head de Diversidade"],
    "Marketing": ["CMO", "Diretor de Marketing", "Head de Marketing", "Gerente de Marketing Digital"],
    "ESG": ["ESG", "Sustentabilidade", "Head de Sustentabilidade"],
    "Compliance": ["Compliance", "Diretor Jurídico", "General Counsel", "Gerente Jurídico"],
}
SENIORIDADES_PADRAO = ["c_suite", "vp", "head", "director", "manager"]
PRIORIDADE_POR_SETOR_PADRAO: dict[str, list[str]] = {
    "educacao": ["TI", "Marketing", "D&I", "RH", "Compliance", "ESG"],
    "saude": ["TI", "Compliance", "Marketing", "RH", "ESG", "D&I"],
    "financeiro": ["Compliance", "TI", "Marketing", "D&I", "ESG", "RH"],
    "ecommerce": ["Marketing", "TI", "D&I", "ESG", "RH", "Compliance"],
    "utilities": ["Compliance", "TI", "ESG", "Marketing", "RH", "D&I"],
    "outro": PRIORIDADE_PADRAO,
}


@dataclass
class Candidato:
    id: str  # "apollo:<id>" ou "web:<n>"
    nome: str  # na busca do Apollo: primeiro nome + sobrenome ofuscado
    cargo: str | None
    origem: Literal["apollo", "web"]
    apollo_id: str | None = None
    area_sugerida: str | None = None
    fonte_url: str | None = None
    linkedin_url: str | None = None


class Escolha(BaseModel):
    candidato_id: str
    area: Area
    motivo: str


class EscolhaMapeador(BaseModel):
    escolhidos: list[Escolha] = Field(description="No máximo uma pessoa por área")
    raciocinio_resumido: str


class PessoaWeb(BaseModel):
    nome: str
    cargo: str
    area: Area
    fonte_url: str
    linkedin_url: str | None = None


class BuscaWebDecisores(BaseModel):
    pessoas: list[PessoaWeb]
    raciocinio_resumido: str


def candidatos_do_apollo(pessoas: list[PessoaBusca]) -> list[Candidato]:
    return [
        Candidato(
            id=f"apollo:{p.id}",
            nome=" ".join(x for x in (p.primeiro_nome, p.sobrenome_ofuscado) if x),
            cargo=p.cargo,
            origem="apollo",
            apollo_id=p.id,
        )
        for p in pessoas
    ]


def cargos_da_busca(titulos: dict[str, list[str]], areas: list[str]) -> list[str]:
    vistos: list[str] = []
    for area in areas:
        for t in titulos.get(area, []):
            if t not in vistos:
                vistos.append(t)
    return vistos


# --- Busca em fontes públicas ------------------------------------------------


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _eh_linkedin(url: str) -> bool:
    host = _host(url)
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def validar_pessoas_web(
    busca: BuscaWebDecisores, urls_consultadas: list[str], areas: list[str]
) -> tuple[list[PessoaWeb], int]:
    """Só quem tem fonte vista na busca e fora do LinkedIn; link de perfil só se apareceu nos resultados."""
    vistas = set(urls_consultadas)
    validas: list[PessoaWeb] = []
    descartadas = 0
    for p in busca.pessoas:
        nome = p.nome.strip()
        if (
            len(nome.split()) < 2
            or p.area not in areas
            or p.fonte_url not in vistas
            or _eh_linkedin(p.fonte_url)
            or any(v.nome.lower() == nome.lower() for v in validas)
        ):
            descartadas += 1
            continue
        linkedin = p.linkedin_url if p.linkedin_url in vistas and _eh_linkedin(p.linkedin_url or "") else None
        if linkedin and "/in/" not in urlsplit(linkedin).path:
            linkedin = None
        validas.append(p.model_copy(update={"nome": nome, "linkedin_url": linkedin}))
    return validas, descartadas


async def buscar_na_web(
    ia: ClienteIA,
    config: WorkerConfig,
    nome_empresa: str,
    dominio: str,
    areas: list[str],
    titulos: dict[str, list[str]],
) -> tuple[list[PessoaWeb], RespostaBusca, int]:
    exemplos = "; ".join(f"{a}: {', '.join(titulos.get(a, [])[:4])}" for a in areas)
    conteudo = (
        f"Organização: {nome_empresa}\nSite oficial: {dominio}\n"
        f"Áreas que faltam: {', '.join(areas)}\nExemplos de cargos por área: {exemplos}"
    )
    resposta = await ia.com_busca_web(
        modelo=config.model_web_search,
        sistema=carregar_prompt("mapeador-web"),
        conteudo=conteudo,
        max_buscas=config.decisores_max_web_searches,
        effort="low",
        max_tokens=4000,
    )
    try:
        busca = BuscaWebDecisores.model_validate(extrair_json(resposta.texto))
    except ValueError:
        busca = BuscaWebDecisores(pessoas=[], raciocinio_resumido="A busca não trouxe pessoas.")
    validas, descartadas = validar_pessoas_web(busca, resposta.urls_consultadas, areas)
    return validas, resposta, descartadas


def candidatos_da_web(pessoas: list[PessoaWeb]) -> list[Candidato]:
    return [
        Candidato(
            id=f"web:{i}",
            nome=p.nome,
            cargo=p.cargo,
            origem="web",
            area_sugerida=p.area,
            fonte_url=p.fonte_url,
            linkedin_url=p.linkedin_url,
        )
        for i, p in enumerate(pessoas, start=1)
    ]


# --- Nome completo de quem o Apollo achou (sem créditos, ADR 0012) --------------


class NomeCompleto(BaseModel):
    id: str
    nome: str
    fonte_url: str
    linkedin_url: str | None = None


class NomesCompletos(BaseModel):
    pessoas: list[NomeCompleto]
    raciocinio_resumido: str


def _partes_apollo(c: Candidato) -> tuple[str, str | None]:
    """Primeiro nome e sobrenome ofuscado ("S***a") de um candidato da busca grátis do Apollo."""
    partes = c.nome.split()
    ofuscado = partes[-1] if len(partes) > 1 and "*" in partes[-1] else None
    return partes[0], ofuscado


def nome_confere(nome: str, primeiro: str, ofuscado: str | None) -> bool:
    """Mesmo primeiro nome e um sobrenome que começa e termina com as letras da abreviação do Apollo."""
    partes = [_sem_acento(p) for p in nome.split()]
    if len(partes) < 2 or partes[0] != _sem_acento(primeiro):
        return False
    letras = (ofuscado or "").replace("*", "")
    if len(letras) < 2:
        return True
    ini, fim = _sem_acento(letras[0]), _sem_acento(letras[-1])
    return any(p.startswith(ini) and p.endswith(fim) for p in partes[1:])


def validar_nomes(
    resposta: NomesCompletos, candidatos: list[Candidato], urls_consultadas: list[str]
) -> tuple[list[Candidato], int]:
    por_id = {c.id: c for c in candidatos}
    vistas = set(urls_consultadas)
    completos: list[Candidato] = []
    descartados = 0
    for p in resposta.pessoas:
        c = por_id.get(p.id)
        primeiro, ofuscado = _partes_apollo(c) if c else ("", None)
        if (
            c is None
            or p.fonte_url not in vistas
            or _eh_linkedin(p.fonte_url)
            or not nome_confere(p.nome, primeiro, ofuscado)
            or any(x.id == c.id for x in completos)
        ):
            descartados += 1
            continue
        linkedin = p.linkedin_url if p.linkedin_url in vistas and _eh_linkedin(p.linkedin_url or "") else None
        completos.append(
            Candidato(
                id=c.id,
                nome=" ".join(p.nome.split()),
                cargo=c.cargo,
                origem="web",
                apollo_id=c.apollo_id,
                area_sugerida=c.area_sugerida,
                fonte_url=p.fonte_url,
                linkedin_url=linkedin,
            )
        )
    return completos, descartados


async def completar_nomes(
    ia: ClienteIA, config: WorkerConfig, nome_empresa: str, dominio: str, candidatos: list[Candidato]
) -> tuple[list[Candidato], RespostaBusca, int]:
    lista = []
    for c in candidatos:
        primeiro, ofuscado = _partes_apollo(c)
        lista.append(
            {"id": c.id, "primeiro_nome": primeiro, "sobrenome_abreviado": ofuscado, "cargo": c.cargo}
        )
    conteudo = (
        f"Organização: {nome_empresa}\nSite oficial: {dominio}\n\n"
        f"Pessoas:\n{json.dumps(lista, ensure_ascii=False, indent=1)}"
    )
    resposta = await ia.com_busca_web(
        modelo=config.model_web_search,
        sistema=carregar_prompt("mapeador-nomes"),
        conteudo=conteudo,
        max_buscas=config.decisores_max_web_searches,
        effort="low",
        max_tokens=4000,
    )
    try:
        nomes = NomesCompletos.model_validate(extrair_json(resposta.texto))
    except ValueError:
        nomes = NomesCompletos(pessoas=[], raciocinio_resumido="A busca não confirmou nomes.")
    completos, descartados = validar_nomes(nomes, candidatos, resposta.urls_consultadas)
    return completos, resposta, descartados


# --- Escolha -----------------------------------------------------------------


# Palavras do cargo que indicam a área. Se o cargo aponta para outra área e não para a escolhida, a escolha
# do modelo é descartada (ex.: "Gerente Regional de TI" não vale como Marketing).
PALAVRAS_DA_AREA = {
    "TI": r"\b(ti|it|tecnologia|technology|informa\w*|cio|cto|sistemas?|infraestrutura|software)\b",
    "RH": r"\b(rh|hr|recursos humanos|human resources|pessoas|people|gente|talentos?|chro)\b",
    "D&I": r"(diversidade|diversity|inclusao|inclusion|acessibilidade|d&i|\bdei\b)",
    "Marketing": (
        r"\b(marketing|cmo|comunica\w*|marca|brand|experiencia do cliente|customer experience)\b"
    ),
    "ESG": r"\b(esg|sustentabilidade|sustainability|responsabilidade social)\b",
    "Compliance": (
        r"\b(compliance|juridic[oa]|legal|counsel|riscos?|risk|privacidade|privacy|ouvidoria|auditoria)\b"
    ),
}


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def area_coerente(cargo: str | None, area: str) -> bool:
    """O cargo não pode indicar só outras áreas. Cargo sem palavra conhecida fica a critério do modelo."""
    texto = _sem_acento(cargo or "")
    indicadas = {a for a, padrao in PALAVRAS_DA_AREA.items() if re.search(padrao, texto)}
    return not indicadas or area in indicadas


def validar_escolha(
    escolha: EscolhaMapeador, candidatos: list[Candidato], maximo: int
) -> tuple[list[tuple[Candidato, Escolha]], int]:
    """Descarta id desconhecido, pessoa repetida, segunda pessoa da mesma área e área que não bate com o
    cargo; corta no máximo."""
    por_id = {c.id: c for c in candidatos}
    validas: list[tuple[Candidato, Escolha]] = []
    descartadas = 0
    for e in escolha.escolhidos:
        c = por_id.get(e.candidato_id)
        if (
            c is None
            or any(x.id == c.id for x, _ in validas)
            or any(y.area == e.area for _, y in validas)
            or not area_coerente(c.cargo, e.area)
            or len(validas) >= maximo
        ):
            descartadas += 1
            continue
        validas.append((c, e))
    return validas, descartadas


async def escolher(
    ia: ClienteIA,
    config: WorkerConfig,
    nome_empresa: str,
    setor: str | None,
    prioridade: list[str],
    candidatos: list[Candidato],
    maximo: int,
) -> tuple[list[tuple[Candidato, Escolha]], EscolhaMapeador, Consumo, str, int]:
    lista = [
        {
            "id": c.id,
            "cargo": c.cargo,
            "origem": "fonte pública" if c.origem == "web" else "base B2B",
            **({"area_indicada_pela_fonte": c.area_sugerida} if c.area_sugerida else {}),
        }
        for c in candidatos
    ]
    conteudo = (
        f"Empresa: {nome_empresa}\nSetor: {setor or 'outro'}\n"
        f"Áreas em ordem de prioridade: {', '.join(prioridade)}\nMáximo de pessoas: {maximo}\n\n"
        f"Candidatos:\n{json.dumps(lista, ensure_ascii=False, indent=1)}"
    )
    escolha, consumo = await ia.estruturado(
        modelo=config.model_triage,
        sistema=carregar_prompt("mapeador"),
        conteudo=conteudo,
        formato=EscolhaMapeador,
        effort="low",
        max_tokens=2000,
    )
    validas, descartadas = validar_escolha(escolha, candidatos, maximo)
    return validas, escolha, consumo, hash_entrada(conteudo), descartadas
