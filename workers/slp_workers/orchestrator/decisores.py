"""Mapeamento de decisores no orquestrador (CONSTITUICAO §7.3, Etapa 4; §13; §15).

Para uma empresa em MAPEANDO_DECISORES:
1. supressão do domínio e disjuntor de créditos do Apollo (`APOLLO_DAILY_CREDIT_CAP`);
2. dados da empresa no Apollo (1 crédito): porte, UF e cidade, que melhoram o score;
3. busca de pessoas no Apollo (sem crédito) e escolha pelo Haiku, uma pessoa por área;
4. se faltarem áreas, busca web em fontes públicas (nunca o LinkedIn) para as áreas que faltam;
5. e-mail profissional de cada escolhida no Apollo (1 crédito cada), validado (domínio, MX, `verified`);
6. grava os contatos, requalifica (Acesso ao decisor) e, com ao menos um e-mail válido, passa a empresa para
   PREPARANDO_ABORDAGEM, onde ela espera a Fase 3. Sem nenhum válido, fica em MAPEANDO_DECISORES.

Só este módulo grava; os agentes devolvem dados validados (§6).
"""

import asyncio
import hashlib
import logging
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Engine, func, or_, select, update

from slp_workers.agents import mapeador, padroes_email
from slp_workers.agents.mapeador import Candidato, Escolha
from slp_workers.db import (
    acoes_agentes,
    contatos,
    empresas,
    eventos,
    ler_config,
    registrar_acao,
    registrar_evento,
    supressao,
)
from slp_workers.llm import ClienteIA, Consumo
from slp_workers.orchestrator.budget import inicio_do_dia
from slp_workers.orchestrator.qualificacao import qualificar_e_gravar
from slp_workers.settings import WorkerConfig
from slp_workers.web.apify import ClienteApify, Verificacao
from slp_workers.web.apollo import ApolloSemCreditos, ClienteApollo, PessoaEnriquecida
from slp_workers.web.dominio import pertence_ao_dominio
from slp_workers.web.emails import ResolvedorMX, tem_mx, validar_email

log = logging.getLogger("slp_workers.decisores")

MAPEANDO_DECISORES = "MAPEANDO_DECISORES"
PREPARANDO_ABORDAGEM = "PREPARANDO_ABORDAGEM"
EVENTOS_DE_MAPEAMENTO = ("decisores_encontrados", "sem_decisores")
ROTULO_STATUS = {
    "valido": "e-mail verificado",
    "nao_verificado": "e-mail não verificado",
    "sem_email": "sem e-mail",
}

UF_POR_ESTADO = {
    "acre": "AC",
    "alagoas": "AL",
    "amapa": "AP",
    "amazonas": "AM",
    "bahia": "BA",
    "ceara": "CE",
    "distrito federal": "DF",
    "federal district": "DF",
    "espirito santo": "ES",
    "goias": "GO",
    "maranhao": "MA",
    "mato grosso": "MT",
    "mato grosso do sul": "MS",
    "minas gerais": "MG",
    "para": "PA",
    "paraiba": "PB",
    "parana": "PR",
    "pernambuco": "PE",
    "piaui": "PI",
    "rio de janeiro": "RJ",
    "rio grande do norte": "RN",
    "rio grande do sul": "RS",
    "rondonia": "RO",
    "roraima": "RR",
    "santa catarina": "SC",
    "sao paulo": "SP",
    "sergipe": "SE",
    "tocantins": "TO",
}


class CreditosEsgotados(Exception):
    def __init__(self, usados: int, teto: int) -> None:
        super().__init__(f"teto diário de créditos do Apollo atingido ({usados} de {teto})")
        self.usados = usados
        self.teto = teto


def uf_do_estado(estado: str | None, pais: str | None) -> str | None:
    if not estado or (pais and pais.strip().lower() not in ("brazil", "brasil")):
        return None
    texto = unicodedata.normalize("NFKD", estado).encode("ascii", "ignore").decode().lower().strip()
    texto = texto.removeprefix("state of ").removeprefix("estado de ").removeprefix("estado do ")
    if len(texto) == 2 and texto.upper() in UF_POR_ESTADO.values():
        return texto.upper()
    return UF_POR_ESTADO.get(texto)


class OrcamentoApifyEsgotado(Exception):
    def __init__(self, usado_usd: Decimal, teto_usd: Decimal) -> None:
        super().__init__(f"teto diário do Apify atingido (US$ {usado_usd:.2f} de US$ {teto_usd:.2f})")
        self.usado_usd = usado_usd
        self.teto_usd = teto_usd


def gasto_apify_do_dia(engine: Engine, usd_brl: Decimal, agora: datetime | None = None) -> Decimal:
    """Gasto do dia com o Apify em US$ (as ações guardam o custo em reais, como as de IA)."""
    with engine.connect() as conn:
        total = conn.scalar(
            select(func.coalesce(func.sum(acoes_agentes.c.custo), 0)).where(
                acoes_agentes.c.agente == "mapeador.apify", acoes_agentes.c.criado_em >= inicio_do_dia(agora)
            )
        )
    return (Decimal(str(total or 0)) / usd_brl).quantize(Decimal("0.0001"))


def creditos_do_dia(engine: Engine, agora: datetime | None = None) -> int:
    with engine.connect() as conn:
        total = conn.scalar(
            select(func.coalesce(func.sum(acoes_agentes.c.creditos), 0)).where(
                acoes_agentes.c.criado_em >= inicio_do_dia(agora)
            )
        )
    return int(total or 0)


@dataclass
class DependenciasDecisores:
    engine: Engine
    ia: ClienteIA
    config: WorkerConfig
    apollo: ClienteApollo
    resolvedor_mx: ResolvedorMX = tem_mx
    apify: ClienteApify | None = None


@dataclass
class Mapeamento:
    deps: DependenciasDecisores
    empresa_id: uuid.UUID
    _escolhidas_apollo: list[tuple[Candidato, Escolha]] | None = None

    # --- registro ---------------------------------------------------------

    async def evento(self, tipo: str, mensagem: str, **dados: Any) -> None:
        await asyncio.to_thread(registrar_evento, self.deps.engine, self.empresa_id, tipo, mensagem, **dados)

    async def acao(
        self,
        agente: str,
        entrada: str,
        saida: dict,
        raciocinio: str | None,
        *,
        consumo: Consumo | None = None,
        creditos: int = 0,
    ) -> None:
        c = consumo or Consumo(modelo="apollo")
        await asyncio.to_thread(
            registrar_acao,
            self.deps.engine,
            agente=agente,
            empresa_id=self.empresa_id,
            entrada_hash=hashlib.sha256(entrada.encode()).hexdigest(),
            saida=saida,
            raciocinio=raciocinio,
            modelo=c.modelo,
            tokens_in=c.tokens_in,
            tokens_out=c.tokens_out,
            custo_brl=c.custo_brl,
            duracao_ms=c.duracao_ms,
            creditos=creditos,
        )

    # --- banco ------------------------------------------------------------

    def _empresa(self) -> Any:
        with self.deps.engine.connect() as conn:
            return conn.execute(select(empresas).where(empresas.c.id == self.empresa_id)).first()

    def _config(self) -> dict:
        with self.deps.engine.connect() as conn:
            return ler_config(conn, "decisores", "icp")

    def _dominio_suprimido(self, dominio: str) -> bool:
        with self.deps.engine.connect() as conn:
            return (
                conn.scalar(select(supressao.c.id).where(supressao.c.dominio == dominio).limit(1)) is not None
            )

    def _email_suprimido(self, email: str) -> bool:
        with self.deps.engine.connect() as conn:
            return conn.scalar(select(supressao.c.id).where(supressao.c.email == email).limit(1)) is not None

    def _existente(self, apollo_id: str | None, email: str | None, nome: str) -> uuid.UUID | None:
        condicoes = [func.lower(contatos.c.nome) == nome.lower()]
        if apollo_id:
            condicoes.append(contatos.c.apollo_id == apollo_id)
        if email:
            condicoes.append(contatos.c.email == email)
        with self.deps.engine.connect() as conn:
            return conn.scalar(
                select(contatos.c.id)
                .where(contatos.c.empresa_id == self.empresa_id, or_(*condicoes))
                .limit(1)
            )

    def _atualizar_contato(self, contato_id: uuid.UUID, valores: dict) -> None:
        """Reprocessar corrige o contato (e-mail, área, cargo) sem duplicar; opt-out nunca é desfeito."""
        with self.deps.engine.begin() as conn:
            conn.execute(update(contatos).where(contatos.c.id == contato_id).values(**valores))

    def _atualizar_empresa(self, valores: dict) -> None:
        with self.deps.engine.begin() as conn:
            conn.execute(update(empresas).where(empresas.c.id == self.empresa_id).values(**valores))

    def _gravar_contato(self, valores: dict) -> None:
        with self.deps.engine.begin() as conn:
            conn.execute(
                contatos.insert().values(
                    id=uuid.uuid4(),
                    empresa_id=self.empresa_id,
                    opt_out=False,
                    criado_em=datetime.now(UTC),
                    **valores,
                )
            )

    def _transitar(self, origem: str, destino: str) -> bool:
        with self.deps.engine.begin() as conn:
            r = conn.execute(
                update(empresas)
                .where(empresas.c.id == self.empresa_id, empresas.c.estado == origem)
                .values(estado=destino)
            )
        return r.rowcount == 1

    # --- etapas -----------------------------------------------------------

    async def _enriquecer_empresa(self, empresa: Any) -> None:
        org = await self.deps.apollo.organizacao(empresa.dominio)
        await self.acao(
            "mapeador.apollo",
            empresa.dominio,
            {"organizacao": org.__dict__ if org else None},
            None,
            creditos=1 if org else 0,
        )
        if org is None:
            return
        valores: dict[str, Any] = {}
        if org.colaboradores:
            valores["porte"] = str(org.colaboradores)
        uf = uf_do_estado(org.estado, org.pais)
        if uf and not empresa.uf:
            valores["uf"] = uf
        if org.cidade and not empresa.cidade:
            valores["cidade"] = org.cidade[:120]
        if valores:
            await asyncio.to_thread(self._atualizar_empresa, valores)
            partes = []
            if "porte" in valores:
                partes.append(f"cerca de {org.colaboradores} colaboradores")
            if "uf" in valores or "cidade" in valores:
                partes.append(" / ".join(x for x in (valores.get("cidade"), valores.get("uf")) if x))
            await self.evento("empresa_enriquecida", "Dados da empresa no Apollo: " + "; ".join(partes) + ".")

    async def _escolher_no_apollo(
        self, empresa: Any, cfg: dict, prioridade: list[str], maximo: int
    ) -> list[tuple[Candidato, Escolha]]:
        titulos = cfg.get("titulos") or mapeador.TITULOS_PADRAO
        pessoas = await self.deps.apollo.buscar_pessoas(
            empresa.dominio,
            mapeador.cargos_da_busca(titulos, prioridade),
            list(cfg.get("senioridades") or mapeador.SENIORIDADES_PADRAO),
            self.deps.config.apollo_max_candidatos,
        )
        await self.acao("mapeador.apollo_busca", empresa.dominio, {"pessoas": len(pessoas)}, None, creditos=0)
        if not pessoas:
            return []
        candidatos = mapeador.candidatos_do_apollo(pessoas)
        validas, escolha, consumo, entrada_hash, descartadas = await mapeador.escolher(
            self.deps.ia, self.deps.config, empresa.nome, empresa.setor, prioridade, candidatos, maximo
        )
        await self.acao(
            "mapeador",
            entrada_hash,
            {**escolha.model_dump(), "descartados": descartadas},
            escolha.raciocinio_resumido,
            consumo=consumo,
        )
        return validas

    async def _completar_na_web(
        self, empresa: Any, cfg: dict, faltam: list[str]
    ) -> list[tuple[Candidato, Escolha]]:
        pessoas, resposta, descartadas = await mapeador.buscar_na_web(
            self.deps.ia,
            self.deps.config,
            empresa.nome,
            empresa.dominio,
            faltam,
            cfg.get("titulos") or mapeador.TITULOS_PADRAO,
        )
        await self.acao(
            "mapeador.web",
            empresa.dominio,
            {"pessoas": [p.model_dump() for p in pessoas], "descartados": descartadas},
            None,
            consumo=resposta.consumo,
        )
        escolhidas = []
        for area in faltam:
            c = next((c for c in mapeador.candidatos_da_web(pessoas) if c.area_sugerida == area), None)
            if c:
                escolhidas.append(
                    (c, Escolha(candidato_id=c.id, area=area, motivo=f"Encontrado em {c.fonte_url}."))
                )
        return escolhidas

    async def _completar_nomes(
        self, empresa: Any, escolhidas: list[tuple[Candidato, Escolha]]
    ) -> list[tuple[Candidato, Escolha]]:
        """Nome completo, em fonte pública, de quem a busca grátis do Apollo achou (ADR 0012)."""
        por_id = {c.id: e for c, e in escolhidas}
        completos, resposta, descartados = await mapeador.completar_nomes(
            self.deps.ia, self.deps.config, empresa.nome, empresa.dominio, [c for c, _ in escolhidas]
        )
        await self.acao(
            "mapeador.web",
            empresa.dominio,
            {"nomes_confirmados": len(completos), "pedidos": len(escolhidas), "descartados": descartados},
            None,
            consumo=resposta.consumo,
        )
        return [(c, por_id[c.id]) for c in completos]

    async def _registrar_contato(self, empresa: Any, c: Candidato, e: Escolha) -> str | None:
        """Busca o e-mail no Apollo, valida e grava. Devolve o status do e-mail ou None se não gravou."""
        p: PessoaEnriquecida | None
        if c.origem == "apollo":
            p = await self.deps.apollo.enriquecer_pessoa(apollo_id=c.apollo_id)
        else:
            p = await self.deps.apollo.enriquecer_pessoa(nome=c.nome, dominio=empresa.dominio)
        await self.acao(
            "mapeador.apollo", c.id, {"pessoa": p.bruto if p else None}, None, creditos=p.creditos if p else 0
        )
        nome = (p.nome if p and p.nome else None) or (c.nome if c.origem == "web" else None)
        if not nome:
            return None
        # Na busca do Apollo a pessoa já veio filtrada pelo domínio da empresa; da web, o registro dela no
        # Apollo precisa apontar para o site da empresa
        site_org = urlsplit(p.org_site or "").hostname if p and p.org_site else None
        confirmada = c.origem == "apollo" or bool(
            p and any(pertence_ao_dominio(h, empresa.dominio) for h in (p.org_dominio, site_org) if h)
        )
        validado = await validar_email(
            p.email if p else None,
            empresa.dominio,
            p.email_status if p else None,
            self.deps.resolvedor_mx,
            organizacao_confirmada=confirmada,
        )
        if validado.email and await asyncio.to_thread(self._email_suprimido, validado.email):
            await self.evento(
                "contato_suprimido",
                f"Um decisor de {e.area} está na lista de supressão e não foi registrado.",
            )
            return None
        apollo_id = (p.id if p else None) or c.apollo_id
        valores = {
            "nome": nome[:200],
            "cargo": ((p.cargo if p else None) or c.cargo or "")[:200] or None,
            "area": e.area,
            "email": validado.email,
            "email_status": validado.status,
            "linkedin_url": ((p.linkedin_url if p else None) or c.linkedin_url or None),
            "fonte": "apollo" if c.origem == "apollo" else "web+apollo",
            "fonte_url": c.fonte_url,
            "apollo_id": apollo_id,
        }
        existente = await asyncio.to_thread(self._existente, apollo_id, validado.email, nome)
        if existente is not None:
            await asyncio.to_thread(self._atualizar_contato, existente, valores)
        else:
            await asyncio.to_thread(self._gravar_contato, valores)
        return validado.status

    async def _caminho_alternativo(
        self, empresa: Any, dec: dict, prioridade: list[str], maximo: int, sem_apollo: str
    ) -> list[tuple[str, str]] | str:
        """Sem Apollo (sem chave ou sem créditos): nomes em fontes públicas, e-mail inferido do padrão da
        empresa e verificado por SMTP no Apify (ADR 0012). Devolve os resultados ou o código de espera."""
        apify = self.deps.apify
        if apify is None or not apify.configurado:
            tipo = "apollo_nao_configurado" if sem_apollo == "nao_configurado" else "apollo_sem_creditos"
            motivo = (
                "O Apollo não está configurado (APOLLO_API_KEY)"
                if sem_apollo == "nao_configurado"
                else "O plano do Apollo está sem créditos neste ciclo"
            )
            await self.evento(
                tipo, f"{motivo} e o Apify não está configurado: o mapeamento de decisores espera."
            )
            return tipo
        teto = self.deps.config.apify_daily_budget_usd
        gasto = await asyncio.to_thread(gasto_apify_do_dia, self.deps.engine, self.deps.config.usd_brl_rate)
        if gasto + apify.custo_usd(maximo * padroes_email.MAX_CANDIDATOS) > teto:
            raise OrcamentoApifyEsgotado(gasto, teto)

        await self.evento(
            "buscando_decisores_alternativo",
            (
                "Apollo sem créditos neste ciclo: "
                if sem_apollo == "sem_creditos"
                else "Apollo não configurado: "
            )
            + "procurando decisores em fontes públicas (sem LinkedIn) e verificando o e-mail no Apify.",
        )
        escolhidas: list[tuple[Candidato, Escolha]] = []
        if sem_apollo == "sem_creditos":
            # A busca de pessoas do Apollo não gasta crédito: diz quem ocupa cada cargo (nome abreviado)
            do_apollo = self._escolhidas_apollo
            if do_apollo is None:
                do_apollo = await self._escolher_no_apollo(empresa, dec, prioridade, maximo)
            if do_apollo:
                escolhidas = await self._completar_nomes(empresa, do_apollo)
        if not escolhidas:
            escolhidas = await self._completar_na_web(empresa, dec, prioridade[:maximo])
        pessoas = [(c, e, padroes_email.candidatos(c.nome, empresa.dominio)) for c, e in escolhidas[:maximo]]
        todos = [email for _, _, lista in pessoas for email in lista]
        verificacoes: dict[str, Verificacao] = await apify.verificar(todos) if todos else {}
        if todos:
            # Sem os endereços no registro: só contagens e situações (coleta mínima)
            custo_usd = apify.custo_usd(len(set(todos)))
            custo_brl = (custo_usd * self.deps.config.usd_brl_rate).quantize(Decimal("0.0001"))
            await self.acao(
                "mapeador.apify",
                empresa.dominio,
                {
                    "verificados": len(verificacoes),
                    "entregaveis": sum(1 for v in verificacoes.values() if v.entregavel),
                    "catch_all": sum(1 for v in verificacoes.values() if v.catch_all),
                },
                None,
                consumo=Consumo(modelo="apify:verificador", custo_brl=custo_brl),
            )
        resultados: list[tuple[str, str]] = []
        for c, e, lista in pessoas:
            entregavel = next((m for m in lista if (v := verificacoes.get(m)) and v.entregavel), None)
            duvidoso = next((m for m in lista if (v := verificacoes.get(m)) and v.smtp_valido), None)
            if entregavel:
                email, status = entregavel, "valido"
            elif duvidoso:
                email, status = duvidoso, "nao_verificado"  # catch-all ou incerto: não serve para envio
            else:
                email, status = None, "sem_email"
            if email and await asyncio.to_thread(self._email_suprimido, email):
                await self.evento(
                    "contato_suprimido",
                    f"Um decisor de {e.area} está na lista de supressão e não foi registrado.",
                )
                continue
            valores = {
                "nome": c.nome[:200],
                "cargo": (c.cargo or "")[:200] or None,
                "area": e.area,
                "email": email,
                "email_status": status,
                "linkedin_url": c.linkedin_url,
                "fonte": "web+apify",
                "fonte_url": c.fonte_url,
                "apollo_id": None,
            }
            existente = await asyncio.to_thread(self._existente, None, email, c.nome)
            if existente is not None:
                await asyncio.to_thread(self._atualizar_contato, existente, valores)
            else:
                await asyncio.to_thread(self._gravar_contato, valores)
            resultados.append((e.area, status))
        return resultados

    def _validos_salvos(self) -> int:
        with self.deps.engine.connect() as conn:
            return int(
                conn.scalar(
                    select(func.count()).where(
                        contatos.c.empresa_id == self.empresa_id,
                        contatos.c.email_status == "valido",
                        contatos.c.opt_out.is_(False),
                    )
                )
                or 0
            )

    async def _concluir(self, resultados: list[tuple[str, str]]) -> str:
        # Conta os contatos válidos já salvos (de rodadas anteriores ou do Apollo), não só os desta rodada
        validos = await asyncio.to_thread(self._validos_salvos)
        await asyncio.to_thread(qualificar_e_gravar, self.deps.engine, self.empresa_id)
        if validos:
            await asyncio.to_thread(self._transitar, MAPEANDO_DECISORES, PREPARANDO_ABORDAGEM)
            detalhes = "; ".join(f"{a} ({ROTULO_STATUS[s]})" for a, s in resultados)
            texto = (
                f"{len(resultados)} decisor(es) encontrado(s): {detalhes}. "
                if resultados
                else f"Nenhum decisor novo nesta busca; a empresa já tem {validos} contato(s) "
                "com e-mail verificado. "
            )
            await self.evento(
                "decisores_encontrados",
                texto + "A empresa segue para preparar a abordagem.",
                validos=validos,
                areas=[a for a, _ in resultados],
            )
            return "decisores_mapeados"
        await self.evento(
            "sem_decisores",
            (
                f"{len(resultados)} decisor(es) encontrado(s), nenhum com e-mail verificado. "
                if resultados
                else "Nenhum decisor encontrado. "
            )
            + "A empresa fica em mapeamento para o vendedor decidir.",
            areas=[a for a, _ in resultados],
        )
        return "sem_decisores"

    async def _caminho_apollo(
        self, empresa: Any, dec: dict, prioridade: list[str], maximo: int
    ) -> list[tuple[str, str]]:
        await self.evento("mapeando_decisores", "Procurando os decisores no Apollo.")
        if self.deps.config.apollo_enrich_org and not empresa.porte:
            await self._enriquecer_empresa(empresa)
            empresa = await asyncio.to_thread(self._empresa)

        escolhidas = await self._escolher_no_apollo(empresa, dec, prioridade, maximo)
        self._escolhidas_apollo = escolhidas  # se faltar crédito adiante, o caminho alternativo reaproveita
        if len(escolhidas) < maximo:
            cobertas = {e.area for _, e in escolhidas}
            faltam = [a for a in prioridade if a not in cobertas][: maximo - len(escolhidas)]
            if faltam:
                await self.evento(
                    "buscando_decisores_web",
                    f"Procurando em fontes públicas decisores de {', '.join(faltam)} (sem LinkedIn).",
                )
                escolhidas += await self._completar_na_web(empresa, dec, faltam)

        resultados: list[tuple[str, str]] = []
        for c, e in escolhidas[:maximo]:
            status = await self._registrar_contato(empresa, c, e)
            if status:
                resultados.append((e.area, status))
        return resultados

    # --- fluxo ------------------------------------------------------------

    async def executar(self) -> str:
        empresa = await asyncio.to_thread(self._empresa)
        if empresa is None or empresa.estado != MAPEANDO_DECISORES or not empresa.dominio:
            return "ignorado"
        if await asyncio.to_thread(self._dominio_suprimido, empresa.dominio):
            await self.evento(
                "dominio_suprimido", "O domínio está na lista de supressão: nenhum decisor buscado."
            )
            return "dominio_suprimido"

        cfg = await asyncio.to_thread(self._config)
        dec = cfg.get("decisores") or {}
        maximo = int(dec.get("max_contatos") or 3)
        areas_icp = [a for a in ((cfg.get("icp") or {}).get("areas_decisoras") or mapeador.AREAS)]
        prioridade_setor = (dec.get("prioridade_por_setor") or mapeador.PRIORIDADE_POR_SETOR_PADRAO).get(
            empresa.setor or "outro"
        )
        prioridade = [a for a in (prioridade_setor or mapeador.PRIORIDADE_PADRAO) if a in areas_icp]

        if not self.deps.apollo.configurado:
            alternativo = await self._caminho_alternativo(empresa, dec, prioridade, maximo, "nao_configurado")
            return alternativo if isinstance(alternativo, str) else await self._concluir(alternativo)

        teto = self.deps.config.apollo_daily_credit_cap
        usados = await asyncio.to_thread(creditos_do_dia, self.deps.engine)
        if usados + 1 + maximo > teto:
            raise CreditosEsgotados(usados, teto)

        try:
            resultados = await self._caminho_apollo(empresa, dec, prioridade, maximo)
        except ApolloSemCreditos:
            alternativo = await self._caminho_alternativo(empresa, dec, prioridade, maximo, "sem_creditos")
            return alternativo if isinstance(alternativo, str) else await self._concluir(alternativo)
        return await self._concluir(resultados)


def ja_mapeada(engine: Engine, empresa_id: uuid.UUID) -> bool:
    with engine.connect() as conn:
        return (
            conn.scalar(
                select(eventos.c.id)
                .where(eventos.c.empresa_id == empresa_id, eventos.c.tipo.in_(EVENTOS_DE_MAPEAMENTO))
                .limit(1)
            )
            is not None
        )


def custo_estimado(maximo: int) -> tuple[int, Decimal]:
    """Créditos máximos por empresa e custo de IA aproximado (Haiku + busca web eventual), em reais."""
    return 1 + maximo, Decimal("0.15")
