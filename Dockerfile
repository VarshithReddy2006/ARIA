# ============================================================
# Stage 1: Build Astro Frontend
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN chmod -R +x node_modules/.bin
RUN npm run build


# ============================================================
# Stage 2: Install Python Dependencies
# ============================================================
FROM python:3.11-slim AS backend-builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    git \
    gcc \
    g++ \
    libc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --no-cache-dir --user -r requirements.txt


# ============================================================
# Stage 3: Production
# ============================================================
FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/appuser

WORKDIR /app


# ------------------------------------------------------------
# Runtime dependencies + unprivileged user
# ------------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd \
    --create-home \
    --uid 10001 \
    --shell /usr/sbin/nologin \
    appuser


# ------------------------------------------------------------
# Python dependencies
# ------------------------------------------------------------
COPY --from=backend-builder --chown=10001:10001 \
    /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH


# ------------------------------------------------------------
# Backend source
# ------------------------------------------------------------
COPY --chown=10001:10001 backend/  ./backend
COPY --chown=10001:10001 core/     ./core
COPY --chown=10001:10001 services/ ./services
COPY --chown=10001:10001 models/   ./models
COPY --chown=10001:10001 storage/  ./storage
COPY --chown=10001:10001 agents/   ./agents
COPY --chown=10001:10001 memory/   ./memory
COPY --chown=10001:10001 utils/    ./utils
COPY --chown=10001:10001 ria/      ./ria
COPY --chown=10001:10001 mcp/      ./mcp
COPY --chown=10001:10001 infrastructure/ ./infrastructure
COPY --chown=10001:10001 pyproject.toml ./pyproject.toml


# ------------------------------------------------------------
# Astro frontend
# ------------------------------------------------------------
COPY --from=frontend-builder --chown=10001:10001 \
    /app/frontend/dist ./frontend/dist


# ------------------------------------------------------------
# Runtime directories
# ------------------------------------------------------------
RUN mkdir -p \
    /app/data \
    /home/appuser/.repo_intelligence/cloned_repos \
    /home/appuser/.cache \
    && chown -R appuser:appuser /app /home/appuser


# ------------------------------------------------------------
# Application configuration
# ------------------------------------------------------------
EXPOSE 8001

ENV APP_ENV=production
ENV LOG_FORMAT=json

USER appuser


# ------------------------------------------------------------
# Health check
# ------------------------------------------------------------
HEALTHCHECK --interval=30s \
    --timeout=5s \
    --start-period=180s \
    --retries=3 \
    CMD ["sh", "-c", "python -c \"import os,urllib.request,sys; port=os.getenv('PORT', os.getenv('API_SERVER_PORT', '8001')); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)\""]


# ------------------------------------------------------------
# Start FastAPI
# ------------------------------------------------------------
CMD ["sh", "-c", "python -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-${API_SERVER_PORT:-8001}}"]