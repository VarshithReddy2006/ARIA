# ============================================================
# Stage 1: Build Astro Frontend
# ============================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
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
COPY --from=backend-builder --chown=appuser:appuser \
    /root/.local /home/appuser/.local

ENV PATH=/home/appuser/.local/bin:$PATH


# ------------------------------------------------------------
# Backend source
# ------------------------------------------------------------
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


# ------------------------------------------------------------
# Astro frontend
# ------------------------------------------------------------
COPY --from=frontend-builder --chown=appuser:appuser \
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
EXPOSE 10000

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
    CMD ["sh", "-c", "python -c \"import os,urllib.request,sys; port=os.getenv('PORT','10000'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status == 200 else 1)\""]


# ------------------------------------------------------------
# Start FastAPI
# ------------------------------------------------------------
CMD ["sh", "-c", "python -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-10000}"]