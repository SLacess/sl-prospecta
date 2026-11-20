"""Agente Guardião (CONSTITUICAO §9, §13, §15.1; ADR 0016 — Fase 3, Tarefa 4, retomada).

Última checagem antes de um toque entrar na fila de envio do Mensageiro (Tarefa 3, ainda não construída).
Avalia `assunto_final`/`corpo_final` — o texto que o vendedor de fato aprovou na Caixa de Aprovação, que
pode ter sido editado em linha e já não é exatamente o que o Crítico avaliou (§7.3 Etapa 6). Supressão e o
limite de 1 link no primeiro contato (§15.2) são checados por regra no orquestrador, sem gastar IA — este
agente só entra depois dessas regras passarem, para a parte que precisa de julgamento: tom, identificação
do remetente/motivo do contato/como sair (§15.1) e honestidade (§2.2). Devolve um modelo validado; nunca
grava no banco. Esquema publicado em packages/schemas/guardiao.schema.json.
"""

from pydantic import BaseModel

from slp_workers.agents.researcher import carregar_prompt, hash_entrada
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.settings import WorkerConfig

AGENTE = "guardiao"


class AvaliacaoGuardiao(BaseModel):
    aprovado: bool
    motivo: str
    raciocinio_resumido: str


def _conteudo(assunto: str, corpo: str, empresa_nome: str, contato_nome: str) -> str:
    return (
        "Mensagem já aprovada pelo vendedor, pronta para a fila de envio:\n"
        f"Para: {contato_nome}, da empresa {empresa_nome}\n"
        f"Assunto: {assunto}\nCorpo:\n{corpo}"
    )


async def avaliar(
    ia: ClienteIA,
    config: WorkerConfig,
    *,
    assunto: str,
    corpo: str,
    empresa_nome: str,
    contato_nome: str,
) -> tuple[AvaliacaoGuardiao, Consumo, str]:
    conteudo = _conteudo(assunto, corpo, empresa_nome, contato_nome)
    avaliacao, consumo = await ia.estruturado(
        modelo=config.model_triage,
        sistema=carregar_prompt("guardiao"),
        conteudo=conteudo,
        formato=AvaliacaoGuardiao,
        effort="low",
        max_tokens=1000,
    )
    return avaliacao, consumo, hash_entrada(conteudo)
