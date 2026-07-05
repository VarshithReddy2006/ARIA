# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | ✅ Active support |
| < 1.0   | ❌ No longer supported |

---

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

To report a vulnerability, email the maintainers directly (contact details in the GitHub profile) or open a [GitHub private security advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability).

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce (proof-of-concept if possible)
- The version you tested against

You will receive an acknowledgement within 72 hours and a status update within 7 days.

---

## Security Architecture

### Authentication

The API can be secured using an optional `API_KEY` configuration (via the environment variable). When configured, all resource-intensive endpoints (cloning, indexing, chat, reports) require clients to authenticate by supplying the API key in one of the following HTTP headers:

1. **X-API-Key Header**:
   ```http
   X-API-Key: your_secret_api_key_here
   ```

2. **Authorization Bearer Token Header**:
   ```http
   Authorization: Bearer your_secret_api_key_here
   ```

If the API key is not configured, the endpoints default to public access for simplified local development. For multi-tenant or production internet-facing deployments, it is highly recommended to configure the `API_KEY` or place a reverse proxy with full user authentication (e.g., nginx + OAuth2 proxy, Cloudflare Access) in front of the API.

### LLM Provider Credentials

- API keys are loaded exclusively from environment variables (`.env` file or OS environment)
- Keys are never logged — only their presence (`bool`) is recorded at startup
- At startup, all configured providers run a `health_check()` that validates credentials using a lightweight, non-quota-consuming API call (e.g., list models)
- Error messages classify the failure type (e.g., `invalid_credential_type`, `missing_credential`) without exposing key values

### Rate Limiting

A sliding-window per-IP rate limiter is implemented in `backend/security_middleware.py`:

- Default: 60 requests per minute per IP
- Configurable via `RATE_LIMIT_PER_MINUTE` environment variable
- Returns `429 Too Many Requests` when exceeded
- Exempt paths: `/health`, `/metrics`, `/api/v1/health`, `/api/v1/metrics`

### Input Validation

- All API request bodies are validated by Pydantic models before reaching business logic
- GitHub repository URLs are validated by `parse_repo_url()` to prevent path traversal
- File paths in graph and symbol operations are sanitized
- SQL queries use parameterized statements throughout

### CORS

CORS is restricted to the configured `FRONTEND_URL`. `allow_credentials=True` is intentionally paired with a specific origin (not a wildcard) as required by the CORS specification and browser security policy.

In production, set `FRONTEND_URL` to your actual frontend domain.

### Transport

The server binds to `0.0.0.0:8001` by default. In production:

- Place behind a TLS-terminating reverse proxy (nginx, Caddy, Cloudflare)
- Set `ALLOWED_HOSTS` to your production hostname(s)
- Set `APP_ENV=production` to enable fail-fast startup validation

### Middleware Stack

Applied in this order to every request:

1. `RequestIdMiddleware` — injects a unique `X-Request-ID` for audit tracing
2. `RateLimitMiddleware` — per-IP sliding window
3. `MetricsMiddleware` — records request counts and durations (no PII)
4. `GZipMiddleware` — compresses responses > 1000 bytes
5. `TrustedHostMiddleware` — validates `Host` header against `ALLOWED_HOSTS`
6. `CORSMiddleware` — validates `Origin` against `FRONTEND_URL`

### Cloned Repository Isolation

Analyzed repositories are cloned to `CLONED_REPOS_PATH` (defaults to `~/.repo_intelligence/cloned_repos`). This path should be:

- Outside the project tree to prevent uvicorn's WatchFiles from triggering reload loops
- On a volume with sufficient space and appropriate permissions
- Not accessible over the network

### Data Persistence

- `data/analysis_store.json` — written atomically via `tmp` file + `os.replace()` to prevent corruption
- `data/chroma_db/` — local ChromaDB persistence; no network exposure
- `data/repo_understanding.db` — SQLite database; no network exposure

---

## Known Limitations

- **No built-in user/session management**: The application supports optional API key access control but does not include multi-user session/credential management. Place a proxy layer in front of the API for multi-tenant production requirements.
- **No request signing**: Internal service-to-service calls are not authenticated.
- **CORS in development**: In development mode, `localhost:4321` is added as an additional allowed origin alongside `FRONTEND_URL`. This is intentional for local development.
- **GitHub token scope**: `GITHUB_TOKEN` is used for cloning and API calls. Use a fine-grained PAT with the minimum required scopes (`contents:read`, `metadata:read`).
