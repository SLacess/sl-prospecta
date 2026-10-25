"""Comandos do worker.

Uso (no contêiner do worker):
    python -m slp_workers.cli retomar          # recoloca na fila quem parou no meio do pipeline
    python -m slp_workers.cli retomar --listar # só mostra quem seria recolocado

`retomar` serve para empresas que ficaram para trás numa mudança de versão: por exemplo, as que já
tinham dossiê (PESQUISANDO) antes de o Auditor existir. Cada uma volta ao orquestrador, que decide
a próxima etapa.
"""

import argparse
import asyncio
import sys

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select

from slp_workers.db import auditorias, empresas, make_engine
from slp_workers.settings import get_config

ESTADOS_EM_ANDAMENTO = ("NOVO", "PESQUISANDO", "AUDITANDO")


def _pendentes() -> list:
    engine = make_engine(get_config().database_url)
    try:
        with engine.connect() as conn:
            auditadas = select(auditorias.c.empresa_id)
            return conn.execute(
                select(empresas.c.id, empresas.c.nome, empresas.c.estado).where(
                    empresas.c.estado.in_(ESTADOS_EM_ANDAMENTO), empresas.c.id.not_in(auditadas)
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


def main() -> int:
    parser = argparse.ArgumentParser(prog="slp_workers.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("retomar", help="Recoloca na fila as empresas paradas no meio do pipeline")
    p.add_argument("--listar", action="store_true", help="Só lista, sem enfileirar")
    args = parser.parse_args()
    if args.cmd == "retomar":
        return retomar(args.listar)
    return 1


if __name__ == "__main__":
    sys.exit(main())
