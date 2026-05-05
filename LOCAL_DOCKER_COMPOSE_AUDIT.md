# Local Docker Compose Audit

Date: 2026-05-05

## Decision

Audit-only. No Docker Compose file, Dockerfile, launcher, deployment config,
runtime source, frontend source, backend route helper, schema, upload, DB, env
file, or protected core file was changed.

The project-level Compose file appears local-only and stale for the active FE7
frontend because it still builds `./frontend`, a path that is not present in the
current checkout. It should not be used as an alpha deployment source without a
dedicated Docker smoke pass and an explicit update/retirement PR.

This audit uses "project-level" for `super-nova-2177/docker-compose.yml`.
There is no `docker-compose.yml` at the repository checkout root.

## Reference Checks Performed

- `git grep -n "docker-compose" -- .`
- `git grep -n "compose.yml" -- .`
- `git grep -n "./frontend" -- .`
- `git grep -n -F "./frontend" -- .`
- `git grep -n "frontend-social-seven" -- .`
- `git grep -n "Dockerfile" -- .`
- Searched `.github/workflows`.
- Searched Railway/Vercel/Docker/package/deployment files.
- Searched local launcher scripts and local development docs.
- Inspected:
  - `super-nova-2177/docker-compose.yml`
  - `super-nova-2177/backend/Dockerfile`
  - `super-nova-2177/frontend-social-seven/Dockerfile`
  - `super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml`
  - `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`
  - Dockerfiles for retained legacy/deployment-sensitive surfaces.

## Compose Files Found

No `docker-compose.yml` exists at the repository root
`D:\synk\FE4-main\docker-compose.yml`.

The active project-level Compose file is:

- `super-nova-2177/docker-compose.yml`

Nested legacy Compose files are:

- `super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`

## Project Compose Audit Result

Path:

- `super-nova-2177/docker-compose.yml`

Observed services:

- `supernova_db`: local Postgres 15 on host port `5433`.
- `supernova_backend`: builds `./backend`, mounts backend folders, runs
  `uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload`, and sets a
  local Postgres `DATABASE_URL`.
- `supernova_frontend`: builds `./frontend` and exposes port `3000`.

Findings:

- `super-nova-2177/frontend` does not exist.
- Active FE7 is `super-nova-2177/frontend-social-seven`, which is not launched
  by this Compose file.
- Local launcher scripts use Python/npm directly through `run_local.py`,
  `start_backend.ps1`, `start_frontend_social_seven.ps1`, and
  `start_supernova.ps1`; they do not invoke Docker Compose.
- GitHub workflows do not invoke Docker Compose.
- Active production docs describe FE7 on Vercel and the FastAPI backend on
  Railway, not this Compose stack.

Classification:

- Stale local-only Compose candidate.
- Do not treat it as an active deployment source.
- Do not delete or rewrite it without a dedicated Docker-local decision and
  smoke test.

## Nested Compose Audit Result

Path:

- `super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml`

Observed services:

- Builds the nested `supernova_2177_ui_weighted` app.
- Runs with Postgres and Redis.
- Exposes port `8888`.

Classification:

- Nested legacy/protected-core-adjacent surface.
- Retained under the existing nested legacy audit gates in
  `NESTED_LEGACY_SURFACES_AUDIT.md`.

Path:

- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`

Observed services:

- Builds `./backend`.
- Builds `./frontend`, another stale local legacy path inside the nested
  backend experiment.
- Uses local Postgres on host port `5433`.

Classification:

- Nested legacy deployment-sensitive candidate.
- Retained under the existing nested legacy audit gates in
  `NESTED_LEGACY_SURFACES_AUDIT.md`.

## Dockerfiles Observed

- `super-nova-2177/backend/Dockerfile`: active backend-adjacent Dockerfile;
  do not change without deployment smoke.
- `super-nova-2177/frontend-social-seven/Dockerfile`: active FE7-adjacent
  Dockerfile, not referenced by the current project Compose file.
- `super-nova-2177/frontend-next/Dockerfile`: retained deployment/auth-sensitive
  legacy surface; see `FRONTEND_NEXT_DEPLOYMENT_AUDIT.md`.
- `super-nova-2177/frontend-social-six/Dockerfile`: retained
  auth-history-sensitive legacy surface; see
  `FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md`.
- `super-nova-2177/backend/supernova_2177_ui_weighted/Dockerfile`: nested
  legacy/protected-core-adjacent Dockerfile.
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/Dockerfile`:
  nested backend experiment Dockerfile.
- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-api/Dockerfile`:
  nested legacy API Dockerfile.

## Manual Checks Needed Before Changing Compose

Before deleting, renaming, updating, or adding warning comments to Compose
files, verify:

1. No Railway project uses any checked-in Compose or Docker path unexpectedly.
2. No external Docker host, compose stack, or runbook still uses
   `super-nova-2177/docker-compose.yml`.
3. No Vercel project root is relying on Dockerfiles from retained legacy
   frontends.
4. A local Docker smoke pass can start the intended backend and active FE7
   equivalent, or the Compose file is explicitly retired.
5. Existing DB volumes and upload/media paths are not expected to be carried by
   this local Compose stack.
6. The active FE7/Railway/Vercel deployment story remains unchanged.

## Future Options

- Keep audit-only status and continue using PowerShell/Python/npm local
  launchers.
- Add warning comments to `super-nova-2177/docker-compose.yml` in a separate
  config-retirement PR.
- Update Compose to launch `frontend-social-seven` only in a dedicated Docker
  modernization PR with local Docker smoke evidence.
- Delete or retire Compose only after manual external checks prove no local or
  deployment process depends on it.

## Rollback

Rollback for this audit-only PR is a single revert of documentation and static
test changes. No Docker config, runtime source, deployment setting, database,
upload file, frontend source, backend route helper, or protected core file is
changed.
