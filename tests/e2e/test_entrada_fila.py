import asyncio
import os
import time
import uuid
from decimal import Decimal

from arq.connections import RedisSettings, create_pool
from arq.worker import Worker

from app.config import get_settings
from app.queue import job_id_processamento
from slp_workers import main as worker_main
from slp_workers.settings import get_config


def _rodar_worker(max_jobs: int = 1) -> None:
    async def _rodar():
        worker = Worker(
            functions=worker_main.WorkerSettings.functions,
            redis_settings=RedisSettings.from_dsn(os.environ["REDIS_URL"]),
            on_startup=worker_main.startup,
            on_shutdown=worker_main.shutdown,
            burst=True,
            max_burst_jobs=max_jobs,
            poll_delay=0.1,
            handle_signals=False,
        )
        try:
            await worker.main()
        finally:
            await worker.close()

    asyncio.run(_rodar())


def _agendado_para_ms(job_id: str) -> float | None:
    async def _ler():
        pool = await create_pool(RedisSettings.from_dsn(os.environ["REDIS_URL"]))
        try:
            return await pool.zscore("arq:queue", job_id)
        finally:
            await pool.aclose()

    return asyncio.run(_ler())


def _tipos(client, headers, empresa_id):
    return [e["tipo"] for e in client.get(f"/empresas/{empresa_id}", headers=headers).json()["eventos"]]


def test_entrada_passa_pela_fila_e_chega_ao_worker(client, headers):
    dominio = f"fluxo-{uuid.uuid4().hex[:8]}.com.br"

    r = client.post("/prospeccao", json={"alvo": f"https://{dominio}/contato"}, headers=headers)
    assert r.status_code == 201, r.text
    empresa_id = r.json()["empresa"]["id"]
    assert r.json()["empresa"]["estado"] == "NOVO"

    _rodar_worker()

    assert _tipos(client, headers, empresa_id) == [
        "entrada_recebida", "enfileirado", "processamento_iniciado", "aguardando_pesquisador",
    ]

    # Mesma empresa por outra forma do endereço: deduplica e o arq não roda o job de novo
    r2 = client.post("/prospeccao", json={"alvo": f"WWW.{dominio.upper()}"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["duplicada"] is True
    assert r2.json()["empresa"]["id"] == empresa_id
    assert _tipos(client, headers, empresa_id)[-1] == "entrada_duplicada"


def test_disjuntor_de_custo_pausa_o_job_no_worker(client, headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "daily_ai_budget_brl", Decimal("0"))
    monkeypatch.setattr(get_config(), "daily_ai_budget_brl", Decimal("0"))

    assert client.get("/governanca/disjuntores", headers=headers).json()["custo"]["atingido"] is True

    r = client.post("/prospeccao", json={"alvo": f"pausa-{uuid.uuid4().hex[:8]}.com.br"}, headers=headers)
    assert r.status_code == 201
    assert r.json()["fila_pausada"] is True
    empresa_id = r.json()["empresa"]["id"]

    _rodar_worker()

    tipos = _tipos(client, headers, empresa_id)
    assert "fila_pausada_custo" in tipos
    assert "processamento_iniciado" not in tipos
    # O job continua na fila, adiado para quando o orçamento reabrir
    agendado = _agendado_para_ms(job_id_processamento(uuid.UUID(empresa_id)))
    assert agendado is not None and agendado > time.time() * 1000 + 60_000
