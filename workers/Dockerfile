# Contexto de build: raiz do repositório (para acessar packages/ e templates/)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pango e HarfBuzz: o WeasyPrint gera o PDF do mini-relatório (a auditoria com navegador fica no worker-audit)
RUN apt-get update     && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0     && rm -rf /var/lib/apt/lists/*

COPY workers/requirements.txt .
RUN pip install -r requirements.txt

COPY workers/slp_workers ./slp_workers
COPY packages ./packages
COPY templates ./templates

RUN useradd --create-home appuser
USER appuser

CMD ["arq", "slp_workers.main.WorkerSettings"]
