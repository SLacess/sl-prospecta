# Contexto de build: raiz do repositório (para acessar packages/ e templates/)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY workers/requirements.txt .
RUN pip install -r requirements.txt

# Fase 1 (auditoria): trocar a base por mcr.microsoft.com/playwright/python
# ou rodar `playwright install --with-deps chromium` aqui.

COPY workers/slp_workers ./slp_workers
COPY packages ./packages
COPY templates ./templates

RUN useradd --create-home appuser
USER appuser

CMD ["arq", "slp_workers.main.WorkerSettings"]
