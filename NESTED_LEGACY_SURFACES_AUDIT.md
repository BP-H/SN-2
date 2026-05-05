# Nested Legacy Surfaces Audit

Date: 2026-05-05

## Decision

Audit-only. No nested folder was deleted, moved, or renamed. No runtime code,
route behavior, package files, lockfiles, deployment settings, or protected core
files were changed.

The nested surfaces under
`super-nova-2177/backend/supernova_2177_ui_weighted/` remain cleanup-sensitive
until a dedicated migration/removal plan exists for each one.

## Reference Checks Performed

- `git grep -n "nova-web" -- .`
- `git grep -n "nova-api" -- .`
- `git grep -n "transcendental_resonance_frontend" -- .`
- `git grep -n "supernovacore.py" -- .`
- Searched `.github/workflows`.
- Searched package files, lockfiles, Dockerfiles, compose files, Vercel/Railway
  files, scripts, install files, docs, imports, and tests.
- Inspected `nova-web/package.json`, `nova-web/package-lock.json`,
  `nova-web/next.config.js`, `nova-web/README.md`, `nova-web/api/main.py`,
  and `nova-web/app/api/feed/route.js`.
- Inspected `nova-api/index.py`, `nova-api/api/main.py`,
  `nova-api/Dockerfile`, and `nova-api/requirements.txt`.
- Inspected `transcendental_resonance_frontend/README.md`,
  `transcendental_resonance_frontend/__main__.py`,
  `transcendental_resonance_frontend/src/main.py`, compatibility wrappers, and
  test references.
- Confirmed protected-core zero-diff expectations are enforced by
  `.github/workflows/local-safe-pr-gates.yml`, `scripts/check_safe.py`,
  CODEOWNERS, and cleanup docs.

## nova-web Audit Result

Path:

- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web`

Observed surface:

- Standalone nested Next app with `package.json`, `package-lock.json`,
  `next.config.js`, `tailwind.config.js`, and `tsconfig.json`.
- Uses `next@14.2.31`, React 18, Three.js, React Three Fiber, Framer Motion,
  and other UI dependencies.
- Contains `app/` routes, `components/`, `public/`, `src/`, `api/main.py`, and
  `app/api/feed/route.js`.
- `app/api/feed/route.js` returns local static feed data.
- `api/main.py` is a FastAPI stub with permissive CORS and sample feed data.
- `README.md` is minimal and references Vercel redeploy history.

References found:

- Cleanup/security docs and dependency triage docs.
- `REPO_STATUS.md`.
- `NESTED_BACKEND_AND_LOCKFILE_CLEANUP_ASSESSMENT.md`.
- `RSC_NEXT_SECURITY_UPDATE_ASSESSMENT.md`.
- `universe/readme.md`, which references `nova-web` components/routes.
- Its own package/config/source files.

Risk:

- Dependency/security-sensitive because it has an independent Next dependency
  tree and lockfile.
- Deployment-sensitive because it contains an API stub and Vercel-like web app
  structure, even though no active repo-level workflow was found pointing at it.
- Not safe to delete with a generic cleanup pass.

Future cleanup gate:

- Verify no Vercel/project root or other deployment points at `nova-web`.
- Decide whether any Three.js/universe UI concepts should be preserved in
  active FE7 before deletion.
- Resolve dependency/security posture separately from active FE7.
- Run package/reference checks and protected-core zero-diff before any removal.

## nova-api Audit Result

Path:

- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-api`

Observed surface:

- Small nested FastAPI service with `index.py`, `api/main.py`, `Dockerfile`,
  and `requirements.txt`.
- `index.py` exposes `GET /api`.
- `api/main.py` exposes `GET /healthz` and `GET /feed` with static sample data.
- Dockerfile starts `uvicorn api.main:app` on port 8000.

References found:

- `REPO_STATUS.md`.
- `LEGACY_CLEANUP_ROADMAP.md`.
- Its own `index.py` comment and local files.

Risk:

- Low visible reference count, but nested backend/deployment-sensitive because
  it has its own Dockerfile and FastAPI app.
- Not safe to delete until manual deployment checks confirm no project uses this
  nested service.

Future cleanup gate:

- Verify no Docker/Railway/Vercel/project-root deployment uses `nova-api`.
- Confirm no docs or experiments still need the sample `/feed` and `/healthz`
  stubs.
- Prefer deletion only in a single-target PR with rollback and protected-core
  zero-diff.

## transcendental_resonance_frontend Audit Result

Path:

- `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend`

Observed surface:

- NiceGUI/Python UI package with `__main__.py`, `ui.py`, `demo.py`,
  `requirements.txt`, `src/`, `tr_pages/`, `ui/`, and many pytest files.
- `src/main.py` registers many pages and starts background tasks.
- `python -m transcendental_resonance_frontend` remains documented.
- `web_ui/__init__.py` and `web_ui/__main__.py` are compatibility wrappers
  importing/running `transcendental_resonance_frontend`.
- `utils/api.py`, `utils/paths.py`, install scripts, docs, and tests reference
  this package.

References found:

- Main nested README/development docs.
- Install scripts for desktop and Android.
- Compatibility wrappers under `web_ui/`.
- `transcendental_resonance/vibe_simulator_engine.py`.
- `utils/api.py` and `utils/paths.py`.
- `tests/test_page_registry.py`.
- Many package-local tests under
  `transcendental_resonance_frontend/tests/`.
- Existing security/hardening assessments.

Risk:

- High cleanup risk. This is not merely a stale folder; it is a large legacy UI
  package with compatibility wrappers, imports, install scripts, and tests.
- Do not rename or delete without a compatibility plan and targeted test matrix.

Future cleanup gate:

- Inventory every import and compatibility wrapper.
- Decide whether `web_ui` compatibility should remain.
- Run the Transcendental Resonance frontend test suite before and after any
  proposed change.
- Keep protected core and active FE7 untouched.

## Protected Core Status

Protected files:

- `super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py`
- `super-nova-2177/frontend-vite-basic/supernovacore.py`

These files were not edited. Cleanup work must continue to keep protected-core
diff zero unless a future PR explicitly follows `CORE_CHANGE_PROTOCOL.md`.

The zero-diff guard is referenced by:

- `.github/workflows/local-safe-pr-gates.yml`
- `scripts/check_safe.py`
- `.github/CODEOWNERS`
- PR and issue templates
- `LEGACY_CLEANUP_ROADMAP.md`
- `MAINTENANCE_AUDIT.md`
- `REPO_STATUS.md`

## Why No Deletion Was Performed

- `nova-web` has a standalone Next dependency tree and API stubs.
- `nova-api` has a standalone FastAPI service and Dockerfile.
- `transcendental_resonance_frontend` has many imports, wrappers, install
  scripts, and tests.
- External deployment/project-root settings were not manually verified.
- Protected core must remain untouched.

## Rollback

This audit-only PR changes documentation and static guards only. Rollback is a
single revert of the audit/status documentation and test updates.
