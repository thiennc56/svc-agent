# syntax=docker/dockerfile:1.7
# svc-agent – AI agent platform (flow + LLM + MCP). Build: docker build -t ecr.digigov.vn/dns/svc-agent:v1.0-<ts> .
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --no-create-home appuser

FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc libpq-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN pip install --no-cache-dir "pip==24.3.1"
COPY requirements.txt .
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir uvloop httptools gunicorn -r requirements.txt

FROM base AS production

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /venv /venv
COPY --chown=appuser:appgroup app/              ./app/
COPY --chown=appuser:appgroup alembic/          ./alembic/
COPY --chown=appuser:appgroup alembic.ini       ./
COPY --chown=appuser:appgroup gunicorn.conf.py  ./
COPY --chown=appuser:appgroup entrypoint.sh     ./
RUN chmod +x ./entrypoint.sh

ENV PATH="/venv/bin:$PATH" \
    WEB_CONCURRENCY=2

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"

CMD ["./entrypoint.sh"]
