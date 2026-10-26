"""Qualificador (CONSTITUICAO §7.3, Etapa 3): score composto com os pesos e as faixas da tabela `config`.

Regra fixa, sem IA (custo zero): cada componente vale de 0 a 100 e traz a justificativa em português, para o
vendedor entender o número e o Analista (§14) recalibrar os pesos. Quem grava é o orquestrador.

    SCORE = 0,30·Fit_ICP + 0,25·Intenção + 0,20·Gravidade das barreiras
          + 0,15·Pressão regulatória + 0,10·Acesso ao decisor
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

REGRA_VERSAO = "regra-v1"

# Padrões das migrações 0001 e 0004; valem se a chave sumir da `config`
PESOS_PADRAO = {
    "fit_icp": 0.30,
    "intencao": 0.25,
    "gravidade_barreiras": 0.20,
    "pressao_regulatoria": 0.15,
    "acessibilidade_decisor": 0.10,
}
FAIXAS_PADRAO = {"quente": 70, "morno": 45}
ICP_PADRAO = {"setores": ["saude", "educacao", "utilities", "ecommerce", "financeiro"], "porte_minimo": 100}
SINAIS_PADRAO = {
    "vaga_pcd_ou_inclusao": 20,
    "relatorio_esg": 20,
    "pagina_acessibilidade": 20,
    "app_ou_portal": 20,
    "outro": 10,
    "mencao_inclusao": 10,
    "mencoes_teto": 20,
}
PRESSAO_PADRAO = {
    "educacao": 90, "utilities": 80, "saude": 75, "financeiro": 75, "ecommerce": 60, "outro": 40,
}

ROTULOS = {
    "fit_icp": "Aderência ao perfil de cliente (ICP)",
    "intencao": "Sinais de interesse",
    "gravidade_barreiras": "Gravidade das barreiras",
    "pressao_regulatoria": "Pressão regulatória do setor",
    "acessibilidade_decisor": "Acesso ao decisor",
}
NOME_SINAL = {
    "vaga_pcd_ou_inclusao": "vaga para PcD ou inclusão",
    "relatorio_esg": "relatório ESG",
    "pagina_acessibilidade": "página de acessibilidade",
    "app_ou_portal": "app ou portal do cliente",
    "outro": "outro sinal",
}
NOME_SETOR = {
    "saude": "saúde",
    "educacao": "educação",
    "utilities": "utilities e concessões",
    "ecommerce": "e-commerce e varejo",
    "financeiro": "bancos e fintechs",
    "outro": "outro setor",
}
UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

Faixa = Literal["quente", "morno", "frio"]


class Componente(BaseModel):
    chave: str
    rotulo: str
    valor: int  # 0–100
    peso: float
    contribuicao: float  # valor × peso, em pontos do score
    justificativa: str


class Qualificacao(BaseModel):
    score: int
    faixa: Faixa
    componentes: list[Componente]
    pesos: dict[str, float]
    faixas: dict[str, int]
    regra_versao: str = REGRA_VERSAO
    raciocinio_resumido: str


@dataclass
class EntradaQualificacao:
    setor: str | None
    uf: str | None
    dominio: str | None
    porte: str | None  # empresas.porte (Apollo, Tarefa 2); hoje quase sempre vazio
    porte_indicios: str | None  # o que o site diz, do dossiê
    sinais: list[dict] = field(default_factory=list)
    mencoes_inclusao: list[dict] = field(default_factory=list)
    nota_auditoria: int = 100
    contatos_validos: int = 0


class ConfigInvalida(ValueError):
    pass


def validar_pesos(pesos: dict[str, float]) -> None:
    if set(pesos) != set(PESOS_PADRAO):
        raise ConfigInvalida(f"os pesos precisam ter exatamente: {', '.join(PESOS_PADRAO)}")
    if any(not 0 <= float(v) <= 1 for v in pesos.values()):
        raise ConfigInvalida("cada peso precisa ficar entre 0 e 1")
    if abs(sum(float(v) for v in pesos.values()) - 1) > 0.001:
        raise ConfigInvalida("os pesos precisam somar 1,00")


def validar_faixas(faixas: dict[str, int]) -> None:
    quente, morno = faixas.get("quente"), faixas.get("morno")
    if not isinstance(quente, int) or not isinstance(morno, int) or not 0 < morno < quente <= 100:
        raise ConfigInvalida("as faixas precisam respeitar 0 < morno < quente ≤ 100")


def faixa_do_score(score: int, faixas: dict[str, int]) -> Faixa:
    if score >= faixas["quente"]:
        return "quente"
    if score >= faixas["morno"]:
        return "morno"
    return "frio"


def _numero_de_colaboradores(porte: str | None) -> int | None:
    """`empresas.porte` guarda faixas como "201-500" ou "1000+"; vale o menor número da faixa."""
    if not porte:
        return None
    numeros = re.findall(r"\d[\d.]*", porte)
    return int(numeros[0].replace(".", "")) if numeros else None


def _fit_icp(e: EntradaQualificacao, icp: dict) -> tuple[int, str]:
    setores = icp.get("setores") or ICP_PADRAO["setores"]
    porte_minimo = int(icp.get("porte_minimo") or ICP_PADRAO["porte_minimo"])
    partes, valor = [], 0

    if e.setor and e.setor in setores:
        valor += 60
        partes.append(f"setor prioritário ({NOME_SETOR.get(e.setor, e.setor)})")
    else:
        partes.append(f"setor fora da lista do ICP ({NOME_SETOR.get(e.setor or 'outro', e.setor)})")

    uf = (e.uf or "").strip().upper()
    if uf in UFS:
        valor += 20
        partes.append(f"atua no Brasil ({uf})")
    elif (e.dominio or "").endswith(".br"):
        valor += 20
        partes.append("atua no Brasil (domínio .br)")
    else:
        partes.append("sem indício de atuação no Brasil")

    colaboradores = _numero_de_colaboradores(e.porte)
    if colaboradores is None:
        valor += 10
        indicio = f'; o site diz: "{e.porte_indicios}"' if e.porte_indicios else ""
        partes.append(f"porte ainda não conhecido, contado como neutro{indicio}")
    elif colaboradores >= porte_minimo:
        valor += 20
        partes.append(f"porte a partir de {porte_minimo} colaboradores ({e.porte})")
    else:
        partes.append(f"porte abaixo de {porte_minimo} colaboradores ({e.porte})")
    texto = "; ".join(partes)
    return valor, texto[0].upper() + texto[1:] + "."


def _intencao(e: EntradaQualificacao, pesos_sinais: dict) -> tuple[int, str]:
    pesos = {**SINAIS_PADRAO, **pesos_sinais}
    contagem: dict[str, int] = {}
    total = 0
    for sinal in e.sinais:
        tipo = sinal.get("tipo") if sinal.get("tipo") in NOME_SINAL else "outro"
        contagem[tipo] = contagem.get(tipo, 0) + 1
        total += int(pesos.get(tipo, 0))
    pontos_mencoes = min(len(e.mencoes_inclusao) * int(pesos["mencao_inclusao"]), int(pesos["mencoes_teto"]))
    total += pontos_mencoes
    valor = min(total, 100)

    partes = [f"{n}× {NOME_SINAL[t]}" for t, n in contagem.items()]
    if e.mencoes_inclusao:
        partes.append(f"{len(e.mencoes_inclusao)} menção(ões) a inclusão no site")
    achado = ("Encontrado: " + ", ".join(partes) + ".") if partes else "Nenhum sinal encontrado no site."
    return valor, (
        f"{achado} Sinais de peso alto (TAC ou recomendação do MP, avaliação do MEC, visitas ao site da "
        "Sinal Link) ainda não são coletados."
    )


def _gravidade(e: EntradaQualificacao) -> tuple[int, str]:
    nota = max(0, min(100, e.nota_auditoria))
    return 100 - nota, f"Nota de acessibilidade {nota} de 100: quanto mais barreiras, maior a necessidade."


def _pressao(e: EntradaQualificacao, pressao_setor: dict) -> tuple[int, str]:
    tabela = {**PRESSAO_PADRAO, **pressao_setor}
    setor = e.setor if e.setor in tabela else "outro"
    return int(tabela[setor]), (
        f"Setor de {NOME_SETOR.get(setor, setor)}: a LBI (art. 63) vale para todos os sites"
        + ("; o setor tem exigências próprias." if setor != "outro" else ".")
    )


def _decisor(e: EntradaQualificacao) -> tuple[int, str]:
    if e.contatos_validos > 0:
        return 100, f"{e.contatos_validos} contato(s) com e-mail válido."
    return 0, "Ainda sem contatos mapeados; o score é recalculado quando os decisores forem encontrados."


def qualificar(
    e: EntradaQualificacao,
    *,
    pesos: dict[str, float] | None = None,
    faixas: dict[str, int] | None = None,
    icp: dict | None = None,
    sinais_pesos: dict | None = None,
    pressao_setor: dict | None = None,
) -> Qualificacao:
    pesos = {k: float(v) for k, v in (pesos or PESOS_PADRAO).items()}
    faixas = {k: int(v) for k, v in (faixas or FAIXAS_PADRAO).items()}
    validar_pesos(pesos)
    validar_faixas(faixas)

    calculos = {
        "fit_icp": _fit_icp(e, icp or {}),
        "intencao": _intencao(e, sinais_pesos or {}),
        "gravidade_barreiras": _gravidade(e),
        "pressao_regulatoria": _pressao(e, pressao_setor or {}),
        "acessibilidade_decisor": _decisor(e),
    }
    componentes = [
        Componente(
            chave=chave,
            rotulo=ROTULOS[chave],
            valor=valor,
            peso=pesos[chave],
            contribuicao=round(valor * pesos[chave], 2),
            justificativa=justificativa,
        )
        for chave, (valor, justificativa) in calculos.items()
    ]
    # Arredonda meio para cima (o round do Python iria para o par: 60,5 → 60)
    score = max(0, min(100, int(sum(c.contribuicao for c in componentes) + 0.5)))
    faixa = faixa_do_score(score, faixas)
    maiores = sorted(componentes, key=lambda c: c.contribuicao, reverse=True)[:2]
    raciocinio = (
        f"Score {score} ({faixa}). Pesaram mais: "
        + " e ".join(f"{c.rotulo.lower()} ({c.valor}/100)" for c in maiores)
        + "."
    )
    return Qualificacao(
        score=score, faixa=faixa, componentes=componentes, pesos=pesos, faixas=faixas,
        raciocinio_resumido=raciocinio,
    )
