"""Nomes das filas e dos jobs (arq). A auditoria tem fila própria, consumida só pelo worker-audit."""

FILA_AUDITORIA = "arq:queue:auditoria"
JOB_AUDITAR_EMPRESA = "auditar_empresa"


def job_id_auditoria(empresa_id: object) -> str:
    """ID fixo por empresa: a mesma auditoria não entra duas vezes na fila."""
    return f"{JOB_AUDITAR_EMPRESA}:{empresa_id}"
