# Deployment

## Local development
Python 3.12 and Node 22+. Run from repository root:
```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
alembic upgrade head
python -m uvicorn app.main:app --reload
```
In another shell: `cd frontend && npm ci && npm run dev`.
Do not export a blank DATABASE_URL; absence selects a local SQLite database in /tmp.
Open port 3000. Public landing is /welcome, analyst workspace is /, API docs are on backend port 8000 /docs.

## Docker: frontend, API and PostgreSQL
Generate a local password, then start:
```bash
cp .env.example .env
# Generate a password and enter it in POSTGRES_PASSWORD inside ignored .env:
python -c 'import secrets; print(secrets.token_hex(32))'
docker compose up --build
```
Never commit .env. Use hexadecimal passwords to avoid URL-encoding mistakes.
Database is private to the Compose network and retained in the postgres_data volume.
Backend waits for database health and runs Alembic migrations before startup.
Frontend waits for backend health. Backend host port 8000 is loopback-only.
Use `docker compose down` to stop without deleting data. `down -v` permanently removes data.
Back up PostgreSQL before schema upgrades; do not run downgrade on production data.

## Hosted HTTPS
1. Provision PostgreSQL and a Python container host with at least 2 GB RAM.
2. Set DATABASE_URL using the postgresql+psycopg dialect. Set TLS options required by the database provider (for example sslmode=verify-full with its trusted CA).
3. Deploy backend/Dockerfile. Its command applies migrations then starts a single API worker.
4. Deploy frontend/Dockerfile or a Next.js host, setting API_URL to the backend HTTPS origin **before build**. The rewrite destination is baked into the build.
5. Set CORS_ORIGINS and PUBLIC_ORIGIN to the exact HTTPS frontend origin, COOKIE_SECURE=true, and HTTPS termination at your provider.
6. Keep API endpoints and the DB behind host-level firewall and resource limits. Configure 2 MB body limits, request timeouts and distributed per-client/per-account rate limiting at the trusted ingress. Do not trust arbitrary forwarded IP headers.
7. Configure SMTP_HOST/PORT/FROM and optional SMTP_USER/PASSWORD, with SMTP_TLS=true. Verify delivery before advertising password reset.
8. Check /api/health, registration/login, account isolation, a synthetic upload, training, SHAP and PDF download.

No hosting credentials or connected deployment account was available during development. No public URL is claimed.
A domain, hosting/database account, secure environment values and SMTP configuration remain deployment prerequisites.
Live processes are not captured by the cloud environment snapshot.

## Data lifecycle and security
Passwords use Argon2id; sessions and reset tokens are stored only as SHA-256 digests.
Sessions expire after 24 hours. Reset tokens expire after 15 minutes, are single-use and revoke all sessions.
Cookies are HttpOnly, SameSite=Strict, and Secure when configured. Cookie-authenticated writes require X-CSRF-Token.
Use the same-origin Next.js proxy so session cookies never need cross-site SameSite=None.
Registration does not verify email ownership; add verification, abuse protections, monitoring and an operational security review before broad public registration.
Reset requests always return the same response. No tokens are returned or logged.
Tests monkeypatch the mail delivery function to capture tokens in memory: no real email-service credentials are required for tests.
SMTP is plaintext only when explicitly disabled for a trusted local mail sink; production must use TLS.

Uploads are ephemeral unless explicitly saved. Saved datasets, investigations, report snapshots and trained model artifacts are user-owned in PostgreSQL.
Account deletion cascades through stored resources, models and sessions. Individual datasets/resources and trained models can be deleted separately.
Report snapshots store input records/model/threshold/review state; opening one restores the analysis for export. Deleting its model can make re-export impossible.
Use encryption at rest and backups with retention controls at the database provider. Do not upload actual card data or personal financial identifiers.

The single in-process training executor supports one active job. Running jobs do not survive restart; completed model artifacts do.
One API worker is required; use an external job queue before horizontal scaling.
The legacy WORKSPACE_TOKEN capability remains optional for trusted local administrators and is not enabled by Compose.
Public demo is anonymous and synthetic; no regulated banking certification is claimed.
Only administrator-controlled local MODEL_ARTIFACT files or artifacts produced by the server are deserialized. No artifact upload endpoint exists.

## Cloud proxy trust
Dockerfiles support an optional BuildKit secret to preserve certificate verification:
```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t fraudshield-backend backend
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t fraudshield-frontend frontend
```
Use the managed environment's trusted combined CA bundle. The secret is not copied into image layers.
Ordinary networks need no CA secret. Do not disable TLS or package signature checks.
