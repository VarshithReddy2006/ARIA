# Deployment Guide

This guide details steps for deploying ARIA in production.

## Docker Deployment (Recommended)

Production deployments use a preconfigured multi-stage Docker build that bundles the static Astro frontend and serves it through the FastAPI backend server.

### 1. Configure the Environment

Ensure your production host has Docker and Docker Compose installed.

Create a `.env` file containing secrets and credentials:
```env
GITHUB_TOKEN=your_github_token_here
DEEPSEEK_API_KEY=your_nvidia_nim_api_key_here
APP_ENV=production
LOG_FORMAT=json
LOG_LEVEL=INFO
```

### 2. Launch using Docker Compose

Deploy the app in detached daemon mode:
```bash
docker compose -f docker-compose.prod.yml up -d --build
```
This command:
1. Builds the production image containing backend binaries and compiled frontend assets.
2. Mounts named volumes to persist index states, graphs, database files, and cloned repositories.
3. Exposes the unified web application on port `8001`.

---

## Persistent Volumes

To prevent losing analyzed repository data during container updates, ensure the following mounts are persisted:
- **`repo-intel-data`**: Maps to `/app/data` (relational stores, Chroma DB files, caching directories).
- **`repo-intel-cloned`**: Maps to `/root/.repo_intelligence/cloned_repos` (cloned repository directories).

---

## Production Security & Rate Limiting

The application embeds built-in middlewares configurable via settings:
- **Allowed Hosts**: Configure `ALLOWED_HOSTS` to limit server access to known hostnames.
- **CORS Origins**: Set `FRONTEND_URL` to your production frontend domain. The middleware uses `allow_credentials=True`, which requires a specific origin — a wildcard will be rejected by browsers.
- **Rate Limiting**: Adjust `RATE_LIMIT_PER_MINUTE` to prevent denial-of-service (default: 60 requests/min). `/health` and `/metrics` are exempt.
- **GZip Compression**: Automatically compresses payload data over 1000 bytes.
- **Log Format**: Set `LOG_FORMAT=json` for structured log aggregation in production.
