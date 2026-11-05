# API (FastAPI) + CLI de cold start na mesma imagem.
# Build context: raiz do repositório.
#   docker build -f infra/docker/api.Dockerfile -t quantumco-api .
# Volume /data guarda os snapshots. Cold start (uma vez, no console do serviço):
#   quantumco snapshot build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY methodology/ /app/methodology/
RUN uv sync --frozen --no-dev

ENV PATH=/app/.venv/bin:$PATH \
    QC_DATA_DIR=/data \
    QC_METHODOLOGY_DIR=/app/methodology/v1

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "quantumco.entrypoints.api.app:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
