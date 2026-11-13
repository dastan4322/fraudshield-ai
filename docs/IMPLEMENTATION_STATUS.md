# Implementation status

Updated: 2026-11-14 (Asia/Almaty).
Branch: `feat/fraudshield-platform`.
Latest verified application commit: `afd09569f0b595ee5e34e6a45743a4d5b030d20c`.
Subsequent status/evidence-only commits record browser scripts, screenshots and this document; use
`git rev-parse HEAD` / the remote branch to identify the current evidence commit.

## Completed and exercised
- Existing history recovered; baseline 52074be retained. No reset or force push.
- Next.js dashboard, landing page, CSV/drop preview, mapping, configurable custom training.
- Search, sorting, risk filtering, pagination, review status and saved investigation snapshots.
- PostgreSQL, SQLAlchemy and Alembic migration upgrade/downgrade/upgrade on an isolated test database.
- Argon2id accounts, hashed expiring session/reset tokens, CSRF, login/logout, reset flow and account deletion.
- Per-user resources, persisted trained models, resource/model deletion and workspace deletion.
- Logistic, forest and XGBoost; train-only preprocessing/calibration; duplicate-feature leakage guard.
- Validation-only Optuna search, SMOTE inside training folds, weighted/baseline/uncalibrated and chronological experiments.
- Held-out metrics, PR/ROC/calibration curves, fixed-precision/budget metrics, cost sensitivity and shift stress.
- Actual permutation SHAP through the full calibrated pipeline, sampled global/individual summaries; additivity tested.
- PDF/HTML/CSV exports; PDF text/structure tested, with a real chart.
- Three-service Docker deployment, health checks, migration startup, pinned runtime dependency closure.
- CI configuration includes PostgreSQL, audits, frontend/backend tests, build and browser integration.

## Measured validation
- Backend: **28 passed, 0 failed**, final run against PostgreSQL after dependency/security updates.
- Frontend: **5 passed, 0 failed**.
- Production Next.js build: passed, including /welcome.
- Runtime dependency audits: no known vulnerabilities from pip-audit; npm production audit reported 0.
- Authenticated Chromium E2E: passed against Docker frontend/API/PostgreSQL, using the final backend image.
  Exercised registration, pagination, save, CSV, train, predict, SHAP, PDF download, logout/login,
  snapshot restoration and account deletion.
- Anonymous Chromium smoke: passed (demo, threshold, filtering, explanations and responsive layout).
- Both Docker images build. Backend health validates database connectivity and trained model readiness.
- 15 synthetic experiment runs completed; aggregate report in synthetic-experiments.json.
- Kaggle-style schema/inference validated using generated fixtures, **not real Kaggle records**.
- One test-runner deprecation warning remains (Starlette's compatibility path for httpx); no test failed.
- Browser tests wait for actual rendered transaction data. A prior network-idle navigation wait timed out;
  that wait was replaced with DOM readiness plus functional assertions, and the authenticated flow passed.
- GitHub-hosted CI execution/status is **not verified**: API access was forbidden.

## ML evidence
All committed metrics are synthetic. Class-weighted tuned PR-AUC:
logistic 0.488, forest 0.446, XGBoost 0.463.
Chronological default PR-AUC: logistic 0.571, forest 0.581, XGBoost 0.591.
The chronological protocol uses fixed defaults rather than parameters chosen using stratified future data.
Exact parameters, splits, costs, curves and limits are in synthetic-experiments.json / methodology.md.
These results do not establish real-world performance or banking suitability.

## External blockers
1. Kaggle request returned proxy CONNECT 403; no Kaggle key/token or credential file was present.
   No actual Kaggle benchmark has run. Supported CLI/manual workflow and fixtures are implemented.
2. GitHub GraphQL returned Forbidden for both PR inspection and creation. No PR creation or merge is claimed.
   Default branch remains at its initial commit until verified otherwise.
3. No Vercel/Render hosting credentials were configured. Public website is **not deployed**.
4. SMTP delivery is not configured/verified. Reset flow is tested with an in-memory delivery replacement;
   no secret or token is exposed through a public reset response.
5. Draft network additions (api.github.com, kaggle.com, www.kaggle.com) and updated environment setup/start
   instructions are saved but not applied/published. Current runtime policy still has no custom allowed hosts.

## Production prerequisites / remaining engineering
- Configure PostgreSQL TLS/backups, HTTPS, secure cookies, SMTP and hosting.
- Verify email ownership before broad public registration; add monitored, distributed ingress abuse controls.
- Move jobs into a durable external queue before multiple workers/horizontal scaling; running jobs are currently volatile.
- Training/experiment row limit is 10,000; the Kaggle CLI uses a documented subset, not full-scale benchmarking.
- SHAP global summaries are bounded samples, not population-wide attribution.
- Saved report snapshots reference models; deleting a model can prevent re-export.
- No compliance certification, financial decision automation or regulated-production readiness is claimed.

## Exact next step
Review/save the network additions in environment settings and publish the prepared environment.
Retry GitHub API access; inspect existing PRs, create/update the PR, inspect required reviews/CI/branch protection,
then merge only if repository rules permit and all required checks pass. Verify main's SHA afterward.
Obtain Kaggle access locally/securely, run the real dataset workflow, publish measured aggregate results only.
Provision hosting/PostgreSQL/SMTP, configure secure environment settings, deploy and validate a real HTTPS URL.
