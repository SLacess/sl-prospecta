"""Mensageiro — envio real pela caixa conectada (CONSTITUICAO §9, §15.2; ADR 0016, Fase 3 Tarefa 4).

Dispara manualmente via `python -m slp_workers.cli enviar` (mesmo padrão de gerar-sequencia e
avaliar-guardiao): Marcos decide quando rodar, sempre podendo pré-visualizar com --listar antes. Sem
disjuntor de bounce nem "Pausar tudo" ainda (Tarefa 4 do plano), o disparo manual é a única rede de
segurança por ora — por isso o Mensageiro não roda num job periódico automático.

Para cada toque aprovado, não enviado e de canal e-mail:
1. roda o Guardião se ele ainda não tiver avaliado o texto final (mesma checagem do `avaliar-guardiao`
   manual); bloqueado pelo Guardião não é enviado — fica visível na Caixa de Aprovação para o vendedor
   decidir (reaprovar com outro texto, por exemplo).
2. escolhe, entre as caixas ativas, a que tem menos envios hoje e ainda não bateu o limite diário
   (rodízio + limite diário, CONSTITUICAO §15.2); sem caixa disponível, não envia nada agora.
3. renova o access_token a partir do refresh_token descriptografado e envia pela Gmail API.
4. grava `envios` e `toques.enviado_em`, e replica a transição de estado que `POST /toques/{id}/enviado`
   já faz hoje (preparando_abordagem -> em_sequencia no primeiro envio confirmado da empresa) — só este
   módulo grava (§6); `enviado_por` fica nulo (quem enviou foi o sistema, não um humano).

Falha ao renovar o token (ex.: caixa desconectada em myaccount.google.com) grava em
`caixas_envio.erro_verificacao` — o mesmo campo que o painel de Caixas de envio já exibe — e essa caixa
fica de fora do rodízio pelo resto desta rodada, para não repetir a mesma falha em cada toque pendente.
Falha no envio em si (Gmail fora do ar, por exemplo) só gera um evento na linha do tempo da empresa; o
toque continua pendente para a próxima rodada.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import Engine, func, select, update

from slp_workers.crypto import ErroCriptografia, descriptografar
from slp_workers.db import caixas_envio, contatos, empresas, envios, registrar_evento, sequencias, toques
from slp_workers.llm import ClienteIA
from slp_workers.orchestrator.budget import inicio_do_dia
from slp_workers.orchestrator.guardiao import DependenciasGuardiao, Guardiao
from slp_workers.outreach.gmail import ClienteGmail, ErroGmail
from slp_workers.settings import WorkerConfig

PREPARANDO_ABORDAGEM = "PREPARANDO_ABORDAGEM"
EM_SEQUENCIA = "EM_SEQUENCIA"

ResultadoMensageiro = Literal[
    "enviado", "bloqueado_pelo_guardiao", "sem_caixa_disponivel", "erro_de_caixa", "erro_de_envio"
]


@dataclass
class DependenciasMensageiro:
    engine: Engine
    ia: ClienteIA
    config: WorkerConfig
    gmail: ClienteGmail
    # Caixas que já falharam nesta rodada (compartilhado entre os `Mensageiro` do mesmo lote do CLI) —
    # evita tentar renovar o token da mesma caixa quebrada a cada toque pendente.
    caixas_invalidas: set[uuid.UUID] = field(default_factory=set)


@dataclass
class Mensageiro:
    deps: DependenciasMensageiro
    toque_id: uuid.UUID

    # --- banco ----------------------------------------------------------------

    def _contexto(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(
                select(
                    toques, sequencias.c.empresa_id, sequencias.c.contato_id,
                    contatos.c.nome.label("contato_nome"), contatos.c.email,
                    empresas.c.nome.label("empresa_nome"),
                )
                .join(sequencias, sequencias.c.id == toques.c.sequencia_id)
                .join(contatos, contatos.c.id == sequencias.c.contato_id)
                .join(empresas, empresas.c.id == sequencias.c.empresa_id)
                .where(toques.c.id == self.toque_id)
            ).first()

    def _caixas_disponiveis(self) -> list[Any]:
        with self.deps.engine.connect() as conn:
            enviados_hoje = (
                select(envios.c.caixa_id, func.count().label("n"))
                .where(envios.c.enviado_em >= inicio_do_dia())
                .group_by(envios.c.caixa_id)
                .subquery()
            )
            linhas = conn.execute(
                select(
                    caixas_envio.c.id, caixas_envio.c.email, caixas_envio.c.nome_remetente,
                    caixas_envio.c.refresh_token_criptografado, caixas_envio.c.limite_diario,
                    func.coalesce(enviados_hoje.c.n, 0).label("enviados_hoje"),
                )
                .select_from(
                    caixas_envio.outerjoin(enviados_hoje, enviados_hoje.c.caixa_id == caixas_envio.c.id)
                )
                .where(caixas_envio.c.ativa.is_(True))
                .order_by(func.coalesce(enviados_hoje.c.n, 0))
            ).all()
        return [c for c in linhas if c.id not in self.deps.caixas_invalidas]

    def _marcar_erro_caixa(self, caixa_id: uuid.UUID, mensagem: str) -> None:
        with self.deps.engine.begin() as conn:
            conn.execute(
                update(caixas_envio).where(caixas_envio.c.id == caixa_id).values(erro_verificacao=mensagem)
            )

    def _gravar_envio(self, caixa_id: uuid.UUID, destinatario: str, gmail_message_id: str) -> bool:
        """True só se gravou de fato — outra rodada pode ter enviado este toque entretanto."""
        agora = datetime.now(UTC)
        with self.deps.engine.begin() as conn:
            linhas = conn.execute(
                update(toques).where(toques.c.id == self.toque_id, toques.c.enviado_em.is_(None)).values(
                    enviado_em=agora
                )
            ).rowcount
            if linhas != 1:
                return False
            conn.execute(
                envios.insert().values(
                    id=uuid.uuid4(), toque_id=self.toque_id, caixa_id=caixa_id, destinatario=destinatario,
                    gmail_message_id=gmail_message_id, enviado_em=agora,
                )
            )
        return True

    def _entrar_em_sequencia_se_primeiro_envio(self, empresa_id: uuid.UUID) -> bool:
        with self.deps.engine.begin() as conn:
            linhas = conn.execute(
                update(empresas)
                .where(empresas.c.id == empresa_id, empresas.c.estado == PREPARANDO_ABORDAGEM)
                .values(estado=EM_SEQUENCIA)
            ).rowcount
        return linhas == 1

    # --- registro ---------------------------------------------------------

    async def evento(
        self, empresa_id: uuid.UUID, contato_id: uuid.UUID, tipo: str, mensagem: str, **dados: Any
    ) -> None:
        await asyncio.to_thread(
            registrar_evento, self.deps.engine, empresa_id, tipo, mensagem, contato_id=contato_id, **dados
        )

    # --- fluxo ------------------------------------------------------------

    async def executar(self) -> ResultadoMensageiro | None:
        linha = await asyncio.to_thread(self._contexto)
        if (
            linha is None
            or linha.decisao_humana != "aprovado"
            or linha.enviado_em is not None
            or linha.canal != "email"
        ):
            return None  # nada pendente, ou não é um toque que o Mensageiro sabe enviar

        if linha.guardiao_resultado is None:
            await Guardiao(
                DependenciasGuardiao(self.deps.engine, self.deps.ia, self.deps.config), self.toque_id
            ).executar()
            linha = await asyncio.to_thread(self._contexto)

        if linha.guardiao_resultado != "aprovado":
            return "bloqueado_pelo_guardiao"

        candidatas = await asyncio.to_thread(self._caixas_disponiveis)
        caixa = next((c for c in candidatas if c.enviados_hoje < c.limite_diario), None)
        if caixa is None:
            return "sem_caixa_disponivel"

        try:
            refresh_token = descriptografar(caixa.refresh_token_criptografado)
            access_token = await asyncio.to_thread(self.deps.gmail.renovar_access_token, refresh_token)
        except (ErroCriptografia, ErroGmail) as exc:
            self.deps.caixas_invalidas.add(caixa.id)
            await asyncio.to_thread(
                self._marcar_erro_caixa, caixa.id,
                f"Não foi possível renovar o acesso: {exc}. Reconecte esta caixa.",
            )
            return "erro_de_caixa"

        assunto = linha.assunto_final or linha.assunto or ""
        corpo = linha.corpo_final or linha.corpo or ""
        try:
            gmail_message_id = await asyncio.to_thread(
                self.deps.gmail.enviar, access_token,
                remetente_nome=caixa.nome_remetente, remetente_email=caixa.email,
                destinatario=linha.email, assunto=assunto, corpo=corpo,
            )
        except ErroGmail as exc:
            await self.evento(
                linha.empresa_id, linha.contato_id, "envio_falhou",
                f"Falha ao enviar para {linha.contato_nome} por {caixa.email}: {exc}",
            )
            return "erro_de_envio"

        gravou = await asyncio.to_thread(self._gravar_envio, caixa.id, linha.email, gmail_message_id)
        if not gravou:
            return None  # outra rodada já enviou este toque entretanto
        await self.evento(
            linha.empresa_id, linha.contato_id, "toque_enviado",
            f"Mensageiro enviou a mensagem para {linha.contato_nome} por {caixa.email} ({linha.canal}).",
        )
        if await asyncio.to_thread(self._entrar_em_sequencia_se_primeiro_envio, linha.empresa_id):
            await self.evento(
                linha.empresa_id, linha.contato_id, "entrou_em_sequencia",
                f"Primeiro envio confirmado ({linha.contato_nome}): a empresa entra em sequência.",
                origem_estado=PREPARANDO_ABORDAGEM, destino_estado=EM_SEQUENCIA,
            )
        return "enviado"
