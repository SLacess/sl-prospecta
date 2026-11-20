"""Comandos do worker.

Uso (no contêiner do worker):
    python -m slp_workers.cli retomar          # recoloca na fila quem parou no meio do pipeline
    python -m slp_workers.cli retomar --listar # só mostra quem seria recolocado
    python -m slp_workers.cli relatorios --faltantes [--listar]  # gera os mini-relatórios que faltam (sem IA)
    python -m slp_workers.cli qualificar --faltantes [--listar]  # dá o score a quem ainda não tem (sem IA)
    python -m slp_workers.cli qualificar --todas [--listar]      # recalcula todos (ex.: pesos novos)
    python -m slp_workers.cli decisores --pendentes [--listar]   # busca decisores (créditos do Apollo + IA)
    python -m slp_workers.cli decisores --empresa <id> [--listar]
    python -m slp_workers.cli gerar-sequencia --pendentes [--listar]  # Estrategista + Redator + Crítico
    python -m slp_workers.cli gerar-sequencia --empresa <id> [--listar]
    python -m slp_workers.cli avaliar-guardiao --pendentes [--listar]  # checagem final antes do envio
    python -m slp_workers.cli avaliar-guardiao --toque <id> [--listar]
    python -m slp_workers.cli enviar --pendentes [--listar]  # Mensageiro: envia pela caixa conectada
    python -m slp_workers.cli enviar --toque <id> [--listar]

`retomar` serve para empresas que ficaram para trás numa mudança de versão: por exemplo, as que já
tinham dossiê (PESQUISANDO) antes do Auditor, ou auditoria sem nota antes do Auditor com IA.
Cada uma volta ao orquestrador, que decide a próxima etapa.
"""

import argparse
import asyncio
import sys

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import exists, select

from slp_workers.db import auditorias, empresas, make_engine, qualificacoes
from slp_workers.settings import get_config

ESTADOS_EM_ANDAMENTO = ("NOVO", "PESQUISANDO", "AUDITANDO")


def _pendentes() -> list:
    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            # A análise com IA tira a empresa de AUDITANDO: quem está nesses estados tem etapa pendente
            return conn.execute(
                select(empresas.c.id, empresas.c.nome, empresas.c.estado).where(
                    empresas.c.estado.in_(ESTADOS_EM_ANDAMENTO)
                )
            ).all()
    finally:
        engine.dispose()


async def _enfileirar(ids: list) -> int:
    pool = await create_pool(RedisSettings.from_dsn(get_config().redis_url))
    novos = 0
    try:
        for empresa_id in ids:
            job = await pool.enqueue_job(
                "processar_empresa", str(empresa_id), _job_id=f"processar_empresa:{empresa_id}"
            )
            novos += job is not None
    finally:
        await pool.aclose()
    return novos


def retomar(listar: bool) -> int:
    pendentes = _pendentes()
    for e in pendentes:
        print(f"{e.estado:<12} {e.nome}")
    if listar:
        print(f"{len(pendentes)} empresa(s) seriam recolocadas na fila.")
        return 0
    novos = asyncio.run(_enfileirar([e.id for e in pendentes]))
    print(f"{novos} de {len(pendentes)} empresa(s) recolocadas na fila (as demais já estavam).")
    return 0


def _analisadas() -> list:
    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            return conn.execute(
                select(empresas.c.id, empresas.c.nome, auditorias.c.id.label("auditoria_id"))
                .join(auditorias, auditorias.c.empresa_id == empresas.c.id)
                .where(auditorias.c.nota.is_not(None))
                .order_by(empresas.c.nome)
            ).all()
    finally:
        engine.dispose()


async def _gerar_faltantes(listar: bool) -> int:
    from slp_workers.audit.artefatos import ArmazenamentoMinio
    from slp_workers.orchestrator.relatorio import chave_relatorio, gerar_com_evento

    config = get_config()
    armazenamento = ArmazenamentoMinio(
        config.minio_endpoint, config.minio_root_user, config.minio_root_password, config.minio_bucket
    )
    faltantes = [
        e
        for e in _analisadas()
        if not await armazenamento.existe(chave_relatorio(e.id, e.auditoria_id, "pdf"))
    ]
    for e in faltantes:
        print(f"sem relatório  {e.nome}")
    if listar:
        print(f"{len(faltantes)} relatório(s) seriam gerados (sem custo de IA).")
        return 0
    engine = make_engine(config.database_url)
    try:
        gerados = 0
        for e in faltantes:
            gerados += await gerar_com_evento(engine, armazenamento, e.id)
    finally:
        engine.dispose()
    print(f"{gerados} de {len(faltantes)} relatório(s) gerados.")
    return 0 if gerados == len(faltantes) else 1


def _para_qualificar(todas: bool) -> list:
    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            analisada = exists().where(
                auditorias.c.empresa_id == empresas.c.id, auditorias.c.nota.is_not(None)
            )
            consulta = select(empresas.c.id, empresas.c.nome, empresas.c.estado).where(analisada)
            if not todas:
                consulta = consulta.where(~exists().where(qualificacoes.c.empresa_id == empresas.c.id))
            return conn.execute(consulta.order_by(empresas.c.nome)).all()
    finally:
        engine.dispose()


def qualificar(todas: bool, listar: bool) -> int:
    from slp_workers.agents.qualificador import ConfigInvalida
    from slp_workers.orchestrator.qualificacao import qualificar_e_gravar

    alvo = _para_qualificar(todas)
    for e in alvo:
        print(f"{e.estado:<20} {e.nome}")
    if listar:
        print(f"{len(alvo)} empresa(s) seriam qualificadas (sem custo de IA).")
        return 0
    engine = make_engine(get_config().database_url)
    try:
        feitas = 0
        for e in alvo:
            try:
                r = qualificar_e_gravar(engine, e.id)
            except ConfigInvalida as exc:
                print(f"Configuração do score inválida: {exc}. Nada foi gravado para as demais.")
                return 1
            if r is not None:
                feitas += 1
                destino = f" → {r.novo_estado}" if r.novo_estado else ""
                print(f"score {r.qualificacao.score:>3} {r.qualificacao.faixa:<6}{destino}  {e.nome}")
    finally:
        engine.dispose()
    print(f"{feitas} de {len(alvo)} empresa(s) qualificadas.")
    return 0


def _para_mapear(empresa_id: str | None) -> list:
    from slp_workers.db import eventos
    from slp_workers.orchestrator.decisores import EVENTOS_DE_MAPEAMENTO, MAPEANDO_DECISORES

    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            consulta = select(empresas.c.id, empresas.c.nome, empresas.c.estado)
            if empresa_id:
                consulta = consulta.where(empresas.c.id == empresa_id)
            else:
                ja = exists().where(
                    eventos.c.empresa_id == empresas.c.id, eventos.c.tipo.in_(EVENTOS_DE_MAPEAMENTO)
                )
                consulta = consulta.where(empresas.c.estado == MAPEANDO_DECISORES, ~ja)
            return conn.execute(consulta.order_by(empresas.c.nome)).all()
    finally:
        engine.dispose()


async def _mapear(alvo: list) -> int:
    from slp_workers.llm import ClienteAnthropic
    from slp_workers.orchestrator.decisores import (
        CreditosEsgotados,
        DependenciasDecisores,
        Mapeamento,
        OrcamentoApifyEsgotado,
    )
    from slp_workers.orchestrator.pipeline import cliente_apify
    from slp_workers.web.apify import ErroApify
    from slp_workers.web.apollo import ClienteApollo, ErroApollo

    config = get_config()
    engine = make_engine(config.database_url)
    deps = DependenciasDecisores(
        engine=engine,
        ia=ClienteAnthropic(config),
        config=config,
        apollo=ClienteApollo(
            config.apollo_api_key, base_url=config.apollo_base_url, timeout_s=config.apollo_timeout_s
        ),
        apify=cliente_apify(config),
    )
    feitas = 0
    try:
        for e in alvo:
            try:
                r = await Mapeamento(deps, e.id).executar()
            except (CreditosEsgotados, OrcamentoApifyEsgotado) as exc:
                print(f"Parado: {exc}. As demais ficam para amanhã.")
                break
            except (ErroApollo, ErroApify) as exc:
                print(f"erro do Apollo/Apify  {e.nome}: {exc}")
                continue
            feitas += r in ("decisores_mapeados", "sem_decisores")
            print(f"{r:<22} {e.nome}")
            if r in ("apollo_nao_configurado", "apollo_sem_creditos"):
                break
    finally:
        engine.dispose()
    print(f"{feitas} de {len(alvo)} empresa(s) mapeadas.")
    return 0


def decisores(empresa_id: str | None, listar: bool) -> int:
    from slp_workers.orchestrator.decisores import creditos_do_dia, custo_estimado, custo_estimado_alternativo

    alvo = _para_mapear(empresa_id)
    for e in alvo:
        print(f"{e.estado:<20} {e.nome}")
    config = get_config()
    if listar:
        engine = make_engine(config.database_url)
        try:
            usados = creditos_do_dia(engine)
        finally:
            engine.dispose()
        creditos, ia = custo_estimado(3)
        print(
            f"{len(alvo)} empresa(s) seriam mapeadas: até {creditos * len(alvo)} crédito(s) do Apollo "
            f"(hoje: {usados} de {config.apollo_daily_credit_cap}) e cerca de R$ {ia * len(alvo):.2f} de IA."
        )
        if config.apify_token:
            alternativo = custo_estimado_alternativo() * len(alvo)
            print(
                f"Se o Apollo estiver sem créditos: cerca de R$ {alternativo:.2f} "
                "no caminho alternativo (Apify)."
            )
        return 0
    return asyncio.run(_mapear(alvo))


def _para_gerar_sequencia(empresa_id: str | None) -> list:
    from slp_workers.orchestrator.sequencia import PREPARANDO_ABORDAGEM

    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            consulta = select(empresas.c.id, empresas.c.nome, empresas.c.estado)
            if empresa_id:
                consulta = consulta.where(empresas.c.id == empresa_id)
            else:
                consulta = consulta.where(empresas.c.estado == PREPARANDO_ABORDAGEM)
            return conn.execute(consulta.order_by(empresas.c.nome)).all()
    finally:
        engine.dispose()


def _contatos_elegiveis(empresa_ids: list) -> int:
    from sqlalchemy import func

    from slp_workers.db import contatos, sequencias

    if not empresa_ids:
        return 0
    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            ja = exists().where(sequencias.c.contato_id == contatos.c.id)
            return (
                conn.scalar(
                    select(func.count())
                    .select_from(contatos)
                    .where(
                        contatos.c.empresa_id.in_(empresa_ids),
                        contatos.c.email_status == "valido",
                        contatos.c.opt_out.is_(False),
                        ~ja,
                    )
                )
                or 0
            )
    finally:
        engine.dispose()


async def _gerar_sequencias(alvo: list) -> int:
    from slp_workers.llm import ClienteAnthropic
    from slp_workers.orchestrator.sequencia import CustoDiarioEsgotado, DependenciasSequencia, Sequencia

    config = get_config()
    engine = make_engine(config.database_url)
    deps = DependenciasSequencia(engine=engine, ia=ClienteAnthropic(config), config=config)
    feitas = 0
    try:
        for e in alvo:
            try:
                r = await Sequencia(deps, e.id).executar()
            except CustoDiarioEsgotado as exc:
                print(f"Parado: {exc}. As demais ficam para amanhã.")
                break
            feitas += bool(r)
            print(f"{len(r)} contato(s)  {e.nome}: {r}")
    finally:
        engine.dispose()
    print(f"{feitas} de {len(alvo)} empresa(s) processadas.")
    return 0


def gerar_sequencia(empresa_id: str | None, listar: bool) -> int:
    from slp_workers.orchestrator.budget import verificar_disjuntor
    from slp_workers.orchestrator.sequencia import custo_estimado_por_contato

    alvo = _para_gerar_sequencia(empresa_id)
    for e in alvo:
        print(f"{e.estado:<20} {e.nome}")
    config = get_config()
    if listar:
        n = _contatos_elegiveis([e.id for e in alvo])
        melhor, pior = custo_estimado_por_contato(config)
        engine = make_engine(config.database_url)
        try:
            disjuntor = verificar_disjuntor(engine)
        finally:
            engine.dispose()
        print(
            f"{len(alvo)} empresa(s), {n} contato(s) elegível(eis): entre R$ {melhor * n:.2f} e "
            f"R$ {pior * n:.2f} de IA (estimativa, não medição real)."
        )
        print(
            f"Gasto de IA hoje: R$ {disjuntor.custo_hoje_brl} de R$ {disjuntor.teto_brl} "
            f"(teto diário, {'atingido' if disjuntor.atingido else 'livre'})."
        )
        return 0
    return asyncio.run(_gerar_sequencias(alvo))


def _para_avaliar_guardiao(toque_id: str | None) -> list:
    from slp_workers.db import contatos, sequencias, toques

    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            consulta = select(
                toques.c.id, toques.c.dia, contatos.c.nome.label("contato_nome")
            ).join(sequencias, sequencias.c.id == toques.c.sequencia_id).join(
                contatos, contatos.c.id == sequencias.c.contato_id
            )
            if toque_id:
                consulta = consulta.where(toques.c.id == toque_id)
            else:
                consulta = consulta.where(
                    toques.c.decisao_humana == "aprovado",
                    toques.c.enviado_em.is_(None),
                    toques.c.guardiao_resultado.is_(None),
                )
            return conn.execute(consulta.order_by(contatos.c.nome)).all()
    finally:
        engine.dispose()


async def _avaliar_guardioes(alvo: list) -> int:
    from slp_workers.llm import ClienteAnthropic
    from slp_workers.orchestrator.guardiao import DependenciasGuardiao, Guardiao

    config = get_config()
    engine = make_engine(config.database_url)
    deps = DependenciasGuardiao(engine=engine, ia=ClienteAnthropic(config), config=config)
    contagem = {"aprovado": 0, "bloqueado": 0}
    try:
        for t in alvo:
            resultado = await Guardiao(deps, t.id).executar()
            if resultado:
                contagem[resultado] += 1
            print(f"{resultado or 'sem_pendencia':<14} dia {t.dia}  {t.contato_nome}")
    finally:
        engine.dispose()
    print(f"{contagem['aprovado']} aprovado(s), {contagem['bloqueado']} bloqueado(s) de {len(alvo)}.")
    return 0


def avaliar_guardiao(toque_id: str | None, listar: bool) -> int:
    alvo = _para_avaliar_guardiao(toque_id)
    for t in alvo:
        print(f"dia {t.dia}  {t.contato_nome}")
    if listar:
        print(f"{len(alvo)} toque(s) pendente(s) de avaliação do Guardião.")
        return 0
    return asyncio.run(_avaliar_guardioes(alvo))


def _para_enviar(toque_id: str | None) -> list:
    from sqlalchemy import or_

    from slp_workers.db import contatos, sequencias, toques

    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            consulta = select(
                toques.c.id, toques.c.dia, contatos.c.nome.label("contato_nome")
            ).join(sequencias, sequencias.c.id == toques.c.sequencia_id).join(
                contatos, contatos.c.id == sequencias.c.contato_id
            )
            if toque_id:
                consulta = consulta.where(toques.c.id == toque_id)
            else:
                consulta = consulta.where(
                    toques.c.decisao_humana == "aprovado",
                    toques.c.enviado_em.is_(None),
                    toques.c.canal == "email",
                    or_(toques.c.guardiao_resultado.is_(None), toques.c.guardiao_resultado == "aprovado"),
                )
            return conn.execute(consulta.order_by(contatos.c.nome)).all()
    finally:
        engine.dispose()


async def _enviar_toques(alvo: list) -> int:
    from slp_workers.llm import ClienteAnthropic
    from slp_workers.orchestrator.mensageiro import DependenciasMensageiro, Mensageiro
    from slp_workers.outreach.gmail import ClienteGmail

    config = get_config()
    engine = make_engine(config.database_url)
    gmail = ClienteGmail(config.google_oauth_client_id, config.google_oauth_client_secret)
    deps = DependenciasMensageiro(engine=engine, ia=ClienteAnthropic(config), config=config, gmail=gmail)
    contagem: dict[str, int] = {}
    try:
        for t in alvo:
            resultado = await Mensageiro(deps, t.id).executar()
            rotulo = resultado or "sem_pendencia"
            contagem[rotulo] = contagem.get(rotulo, 0) + 1
            print(f"{rotulo:<22} dia {t.dia}  {t.contato_nome}")
    finally:
        engine.dispose()
    for rotulo, n in contagem.items():
        print(f"{n} {rotulo}")
    return 0


def enviar(toque_id: str | None, listar: bool) -> int:
    from slp_workers.db import caixas_envio

    alvo = _para_enviar(toque_id)
    for t in alvo:
        print(f"dia {t.dia}  {t.contato_nome}")
    if listar:
        engine = make_engine(get_config().database_url)
        try:
            with engine.connect() as conn:
                caixas = conn.execute(
                    select(caixas_envio.c.email, caixas_envio.c.limite_diario).where(
                        caixas_envio.c.ativa.is_(True)
                    )
                ).all()
        finally:
            engine.dispose()
        if not caixas:
            print("Nenhuma caixa de envio ativa conectada — nada seria enviado (ADR 0016).")
        else:
            print(
                f"{len(caixas)} caixa(s) ativa(s): "
                + ", ".join(f"{c.email} (até {c.limite_diario}/dia)" for c in caixas)
            )
        print(f"{len(alvo)} toque(s) pronto(s) para o Mensageiro tentar enviar.")
        return 0
    return asyncio.run(_enviar_toques(alvo))


def main() -> int:
    parser = argparse.ArgumentParser(prog="slp_workers.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("retomar", help="Recoloca na fila as empresas paradas no meio do pipeline")
    p.add_argument("--listar", action="store_true", help="Só lista, sem enfileirar")
    r = sub.add_parser("relatorios", help="Gera os mini-relatórios em PDF que ainda não existem")
    r.add_argument(
        "--faltantes", action="store_true", required=True, help="Só as auditorias analisadas sem PDF"
    )
    r.add_argument("--listar", action="store_true", help="Só lista, sem gerar")
    q = sub.add_parser("qualificar", help="Calcula o score (Qualificador, sem IA)")
    grupo = q.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--faltantes", action="store_true", help="Só as analisadas que ainda não têm score")
    grupo.add_argument("--todas", action="store_true", help="Recalcula todas as analisadas")
    q.add_argument("--listar", action="store_true", help="Só lista, sem calcular")
    d = sub.add_parser("decisores", help="Busca os decisores (Mapeador: Apollo + fontes públicas)")
    grupo_d = d.add_mutually_exclusive_group(required=True)
    grupo_d.add_argument(
        "--pendentes", action="store_true", help="Empresas em MAPEANDO_DECISORES ainda sem busca"
    )
    grupo_d.add_argument("--empresa", help="Só esta empresa (id), se estiver em MAPEANDO_DECISORES")
    d.add_argument("--listar", action="store_true", help="Só lista e estima os créditos, sem buscar")
    s = sub.add_parser(
        "gerar-sequencia", help="Estrategista + Redator + Crítico (CONSTITUICAO §7.3, Etapas 5-6)"
    )
    grupo_s = s.add_mutually_exclusive_group(required=True)
    grupo_s.add_argument("--pendentes", action="store_true", help="Empresas em PREPARANDO_ABORDAGEM")
    grupo_s.add_argument("--empresa", help="Só esta empresa (id), se estiver em PREPARANDO_ABORDAGEM")
    s.add_argument("--listar", action="store_true", help="Só lista e estima o custo de IA, sem gerar")
    g = sub.add_parser(
        "avaliar-guardiao", help="Checagem final de compliance/tom antes do envio (ADR 0016)"
    )
    grupo_g = g.add_mutually_exclusive_group(required=True)
    grupo_g.add_argument(
        "--pendentes", action="store_true", help="Toques aprovados, não enviados e ainda não avaliados"
    )
    grupo_g.add_argument("--toque", help="Só este toque (id), reavalia mesmo se já tiver resultado")
    g.add_argument("--listar", action="store_true", help="Só lista, sem avaliar")
    m = sub.add_parser("enviar", help="Mensageiro: envia pela caixa conectada (ADR 0016, Tarefa 3)")
    grupo_m = m.add_mutually_exclusive_group(required=True)
    grupo_m.add_argument(
        "--pendentes", action="store_true", help="Toques aprovados, não enviados, canal e-mail"
    )
    grupo_m.add_argument("--toque", help="Só este toque (id)")
    m.add_argument("--listar", action="store_true", help="Só lista as caixas ativas e os toques, sem enviar")
    args = parser.parse_args()
    if args.cmd == "retomar":
        return retomar(args.listar)
    if args.cmd == "relatorios":
        return asyncio.run(_gerar_faltantes(args.listar))
    if args.cmd == "qualificar":
        return qualificar(args.todas, args.listar)
    if args.cmd == "decisores":
        return decisores(args.empresa, args.listar)
    if args.cmd == "gerar-sequencia":
        return gerar_sequencia(args.empresa, args.listar)
    if args.cmd == "avaliar-guardiao":
        return avaliar_guardiao(args.toque, args.listar)
    if args.cmd == "enviar":
        return enviar(args.toque, args.listar)
    return 1


if __name__ == "__main__":
    sys.exit(main())
