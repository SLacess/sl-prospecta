"""Disjuntor automático de bounce (CONSTITUICAO §13, §15.1; ADR 0016, Tarefa 4).

Sem Google Postmaster Tools (lacuna aceita na ADR 0016), lê a própria caixa via `gmail.readonly`: busca
notificações de devolução (`from:mailer-daemon`) recebidas nas últimas 24h em cada caixa ativa, soma
contra os envios dessa caixa no mesmo período e, passando de 3% (CONSTITUICAO §13), pausa toda a operação
de envio. Cada devolução também é cruzada com os destinatários recentes da caixa para extrair o endereço
que rejeitou e suprimi-lo (CONSTITUICAO §15.1) — não insiste num e-mail morto.

Ao contrário do Mensageiro, automatizar isto é seguro: esta rotina só lê e, na pior hipótese, pausa o
envio — nunca manda e-mail. Por isso roda num cron do arq (a cada 15 minutos, mesma cadência do
heartbeat em `main.py`), além de poder ser chamada manualmente via `python -m slp_workers.cli
verificar-bounce`.
"""

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, select

from slp_workers.crypto import ErroCriptografia, descriptografar
from slp_workers.db import caixas_envio, envios, supressao
from slp_workers.orchestrator.operacao import pausar
from slp_workers.outreach.gmail import ClienteGmail, ErroGmail

LIMIAR_BOUNCE = Decimal("0.03")  # CONSTITUICAO §13: taxa de rejeição > 3% em 24h
JANELA = timedelta(hours=24)
_PADRAO_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass(frozen=True)
class ResultadoBounce:
    total_envios: int
    total_bounces: int
    suprimidos: list[str]
    pausou: bool


@dataclass
class DependenciasBounce:
    engine: Engine
    gmail: ClienteGmail


@dataclass
class DisjuntorBounce:
    deps: DependenciasBounce
    caixas_com_erro: list[str] = field(default_factory=list)

    # --- banco ----------------------------------------------------------------

    def _caixas_ativas(self) -> list[Any]:
        with self.deps.engine.connect() as conn:
            return conn.execute(select(caixas_envio).where(caixas_envio.c.ativa.is_(True))).all()

    def _destinatarios_recentes(self, caixa_id: uuid.UUID, desde: datetime) -> list[str]:
        with self.deps.engine.connect() as conn:
            linhas = conn.execute(
                select(envios.c.destinatario).where(
                    envios.c.caixa_id == caixa_id, envios.c.enviado_em >= desde
                )
            ).all()
        return [linha.destinatario.lower() for linha in linhas]

    def _suprimir_se_novo(self, email: str) -> bool:
        with self.deps.engine.begin() as conn:
            ja_suprimido = conn.scalar(select(supressao.c.id).where(supressao.c.email == email).limit(1))
            if ja_suprimido:
                return False
            conn.execute(
                supressao.insert().values(
                    id=uuid.uuid4(), email=email,
                    motivo="bounce automático detectado pelo disjuntor (ADR 0016)",
                )
            )
        return True

    # --- fluxo ------------------------------------------------------------

    def _destinatario_devolvido(self, snippet: str, candidatos: set[str]) -> str | None:
        encontrados = {e.lower() for e in _PADRAO_EMAIL.findall(snippet)}
        return next(iter(encontrados & candidatos), None)

    def executar(self) -> ResultadoBounce:
        desde = datetime.now(UTC) - JANELA
        total_envios = 0
        total_bounces = 0
        suprimidos: list[str] = []

        for caixa in self._caixas_ativas():
            destinatarios = self._destinatarios_recentes(caixa.id, desde)
            total_envios += len(destinatarios)
            try:
                access_token = self.deps.gmail.renovar_access_token(
                    descriptografar(caixa.refresh_token_criptografado)
                )
                snippets = self.deps.gmail.listar_bounces(access_token, desde=desde)
            except (ErroCriptografia, ErroGmail) as exc:
                self.caixas_com_erro.append(f"{caixa.email}: {exc}")
                continue  # uma caixa com problema não impede checar as outras

            total_bounces += len(snippets)
            candidatos = set(destinatarios)
            for snippet in snippets:
                email = self._destinatario_devolvido(snippet, candidatos)
                if email and self._suprimir_se_novo(email):
                    suprimidos.append(email)

        pausou = False
        if total_envios > 0 and Decimal(total_bounces) / Decimal(total_envios) > LIMIAR_BOUNCE:
            taxa = Decimal(total_bounces) / Decimal(total_envios)
            pausar(
                self.deps.engine,
                motivo=f"Disjuntor de bounce: {taxa:.1%} de devolução em 24h (teto: 3%).",
                origem="disjuntor_bounce",
            )
            pausou = True
        return ResultadoBounce(
            total_envios=total_envios, total_bounces=total_bounces, suprimidos=suprimidos, pausou=pausou
        )
