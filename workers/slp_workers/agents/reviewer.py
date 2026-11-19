"""Agente Crítico (CONSTITUICAO §6, §9.4 e §7.3 Etapa 6).

Avalia a mensagem do Redator em 8 critérios (0-10 cada); a nota final é o mínimo entre eles — um só
critério fraco reprova a mensagem, não a média (§7.3 Etapa 6: "abaixo de 8 em qualquer critério").
Devolve um modelo validado ao orquestrador; nunca grava no banco e nunca decide reescrever — isso é do
orquestrador. Esquema publicado em packages/schemas/critica.schema.json.
"""

from pydantic import BaseModel, Field

from slp_workers.agents.copywriter import Redacao
from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.settings import WorkerConfig

AGENTE = "critico"


class CriteriosCritico(BaseModel):
    especificidade: int = Field(ge=0, le=10)
    veracidade: int = Field(ge=0, le=10)
    humanidade: int = Field(ge=0, le=10)
    clareza: int = Field(ge=0, le=10)
    valor: int = Field(ge=0, le=10)
    honestidade: int = Field(ge=0, le=10)
    brevidade: int = Field(ge=0, le=10)
    acessibilidade: int = Field(ge=0, le=10)


class Critica(BaseModel):
    criterios: CriteriosCritico
    nota: int = Field(ge=0, le=10, description="O menor valor entre os critérios, não a média")
    aprovado: bool
    motivo: str
    raciocinio_resumido: str


def _conteudo(redacao: Redacao, achados: list[dict], empresa_nome: str, resumo_dossie: list[str]) -> str:
    lista_achados = (
        "\n".join(
            f"- {a['titulo']} — {a['impacto_humano']} "
            f"(critério WCAG {a.get('criterio_wcag') or 'não identificado'}, página: {a['pagina_url']})"
            for a in achados
        )
        or "(nenhum achado confirmado)"
    )
    resumo = "\n".join(f"- {linha}" for linha in resumo_dossie)
    return (
        f"Mensagem a avaliar:\nAssunto: {redacao.assunto}\nCorpo:\n{redacao.corpo}\n\n"
        f"Fatos usados pelo redator: {redacao.fatos_usados}\nÂngulo: {redacao.angulo}\n\n"
        f"Dados verificados para conferência:\n"
        f"Empresa: {empresa_nome}\n"
        f"Resumo:\n{resumo}\n\n"
        f"Achados da auditoria:\n{lista_achados}"
    )


async def avaliar(
    ia: ClienteIA,
    config: WorkerConfig,
    *,
    redacao: Redacao,
    achados: list[dict],
    empresa_nome: str,
    resumo_dossie: list[str],
) -> tuple[Critica, Consumo, str]:
    conteudo = _conteudo(redacao, achados, empresa_nome, resumo_dossie)
    critica, consumo = await ia.estruturado(
        modelo=config.model_analysis,
        sistema=carregar_prompt("reviewer"),
        conteudo=conteudo,
        formato=Critica,
        effort="medium",
        max_tokens=4000,
    )
    return critica, consumo, hash_entrada(conteudo)
