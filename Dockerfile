# Stage 1: Build the Astro Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Install Python dependencies
FROM python:3.11-slim AS backend-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git gcc g++ libc-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 3: Production Image
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser

WORKDIR /app

# Runtime OS deps + dedicated unprivileged runtime account
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

# Copy Python packages into the runtime user's home so they are readable non-root
COPY --from=backend-builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# ---------------------------------------------------------------------------
# First-party runtime packages.
# Every package below is imported while serving traffic:
#   backend  — FastAPI app, routers, middleware
#   core     — config, cache, observability, build pipeline
#   services — analysis/chat/LLM business logic
#   models   — Pydantic schemas
#   storage  — SQLite migrations, JSON snapshot store
#   agents   — issue mapper / evaluator agents
#   memory   — ChromaDB store adapter
#   utils    — safe subprocess runner (backend.routers.repositories)
#   ria      — composition root (backend.api) + REST exceptions
#              (backend.exception_handlers)
#   mcp      — MCP server exposed via `backend.cli mcp`
# ---------------------------------------------------------------------------
COPY --chown=appuser:appuser backend/  ./backend
COPY --chown=appuser:appuser core/     ./core
COPY --chown=appuser:appuser services/ ./services
COPY --chown=appuser:appuser models/   ./models
COPY --chown=appuser:appuser storage/  ./storage
COPY --chown=appuser:appuser agents/   ./agents
COPY --chown=appuser:appuser memory/   ./memory
COPY --chown=appuser:appuser utils/    ./utils
COPY --chown=appuser:appuser ria/      ./ria
COPY --chown=appuser:appuser mcp/      ./mcp
COPY --chown=appuser:appuser pyproject.toml ./pyproject.toml

# Copy built frontend code to be served by the backend static file mount
COPY --from=frontend-builder --chown=appuser:appuser /app/frontend/dist ./frontend/dist

# Writable runtime directories (analysis store, SQLite, Chroma, clones, model cache)
RUN mkdir -p /app/data \
             /home/appuser/.repo_intelligence/cloned_repos \
             /home/appuser/.cache \
 && chown -R appuser:appuser /app /home/appuser

EXPOSE 8001
ENV APP_ENV=production
ENV LOG_FORMAT=json

USER appuser

# Liveness probe against the public /health endpoint (no auth required).
# start-period covers embedding-model warm-up and LLM provider validation.
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4).status == 200 else 1)"]

# Startup command running the FastAPI backend via uvicorn
CMD ["python", "-m", "uvicorn", "backend.api:app", "--host", "0.0.0.0", "--port", "8001"]
