# Deployment and privacy

## Local Docker
Run `docker compose up --build` at repository root. Open port 3000. Backend port 8000 binds loopback only; Swagger is at /docs on that port.
For private training set a random WORKSPACE_TOKEN in your shell or a local ignored .env before starting.
The token is a single-administrator capability, not a multi-user account system. Do not share it.

## Hosted deployment
Deploy backend/Dockerfile to a Python container host with at least 2 GB memory.
Keep one worker: models and jobs are process-local. Check /api/health after initial training.
Deploy frontend on a Next.js-compatible host (or frontend/Dockerfile), setting API_URL to the backend's HTTPS URL **before building**; rewrites are baked into the build.
Set CORS_ORIGINS to the exact frontend origin. Enable HTTPS at the host and configure request body limits (2 MB), request timeouts (60 seconds), training rate limits, and trusted proxy IP handling.
Do not trust arbitrary forwarded IP headers. In-process limits are only per instance and are not a distributed abuse-prevention service.
No hosting account or domain is provisioned by this repository. No public deployment has been verified.

## Retention
CSV uploads, custom models and jobs live in process memory; restart deletes them.
The authenticated DELETE /api/workspace operation deletes all custom models and completed jobs.
This is one private workspace per deployment; do not expose it as multi-tenant hosting.
No database, passwords, analytics trackers, or raw record logging are used.
Persistent authenticated accounts, PostgreSQL migrations and cross-worker job queues are future work.
Use synthetic data in public deployments; never send real card data or personal financial identifiers.
Use resource and network limits at your host. Do not expose the Docker daemon.
Joblib is loaded only from administrator-configured MODEL_ARTIFACT; untrusted artifacts can execute code.

## Cloud build verification
Both images were built and run in the development environment. Where an HTTPS inspection
proxy is present, the Dockerfiles support an optional BuildKit CA secret without disabling TLS:
```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t fraudshield-backend backend
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t fraudshield-frontend frontend
```
Use your environment's trusted combined CA bundle, not an untrusted downloaded certificate.
No CA secret is needed on ordinary networks. The certificate is not stored in an image layer.
