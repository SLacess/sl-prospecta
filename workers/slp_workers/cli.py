"""Comandos do worker.

Uso (no contêiner do worker):
    python -m slp_workers.cli retomar          # recoloca na fila quem parou no meio do pipeline
    python -m slp_workers.cli retomar --listar # só mostra quem seria recolocado
    python -m slp_workers.cli relatorios --faltantes [--listar]  # gera os mini-relatórios que faltam (sem IA)
    python -m slp_workers.cli qualificar --faltantes [--listar]  # dá o score a quem ainda não tem (sem IA)
    python -m slp_workers.cli qualificar --todas [--listar]      # recalcula todos (ex.: pesos novos)

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
    args = parser.parse_args()
    if args.cmd == "retomar":
        return retomar(args.listar)
    if args.cmd == "relatorios":
        return asyncio.run(_gerar_faltantes(args.listar))
    if args.cmd == "qualificar":
        return qualificar(args.todas, args.listar)
    return 1


if __name__ == "__main__":
    sys.exit(main())
