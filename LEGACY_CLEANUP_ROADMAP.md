# Legacy Cleanup Roadmap

Branch: `cleanup/legacy-cleanup-roadmap`

Title: `[codex] Add legacy cleanup roadmap`

## Goal

Move toward one active frontend and one active backend without weakening the
SuperNova Core contract or changing production behavior.

This PR is documentation-first. It does not delete legacy source folders, change
runtime behavior, change deployment config, or edit protected core files.

Current checkpoint: `CLEANUP_STABILITY_CHECKPOINT.md` pauses broad cleanup after
the completed launcher/source retirements and deployment-sensitive audits. Treat
manual alpha smoke, branch protection, and durable media storage as higher
priority than additional legacy deletion until that checkpoint changes.

Cleanup inventories are read-only. Retained/deferred entries are not deletion
approval, and completed/deleted entries should not be reintroduced as active
candidates.

## Protected Core

Absolute protected file:

- `super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py`

This file is the constitutional core source of truth. Cleanup work must not edit,
move, rename, delete, reformat, or copy logic from it. Any change to core
semantics must follow `CORE_CHANGE_PROTOCOL.md`.

Required guard for cleanup PRs:

```powershell
git diff --exit-code HEAD -- super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py
```

## Active Production Surfaces

| Surface | Status | Cleanup rule |
| --- | --- | --- |
| `super-nova-2177/frontend-social-seven` | Active frontend | Do not delete or relocate. |
| `super-nova-2177/backend/app.py` | Active backend API | Do not delete or replace. |
| `super-nova-2177/app.py` | Railway compatibility entrypoint | Preserve unless deployment is deliberately migrated. |
| `NEXT_PUBLIC_API_URL` | Active FE7 API origin env var | Preserve name and behavior. |
| `DATABASE_URL` | Active backend DB env var | Preserve name and behavior. |
| `super-nova-2177/protocol/` and `super-nova-2177/backend/protocol/` | Active protocol docs/routes where currently used | Do not delete as legacy frontend cleanup. |

## Cleanup Policy

- Start with assessment and reference checks.
- Do not delete legacy source folders in a mixed cleanup PR.
- A deletion PR must name exactly one target folder or one generated-artifact class.
- Each deletion PR must include reference checks for package files, deployment
  config, Dockerfiles, README/docs, scripts, imports, and CI/workflows.
- Each deletion PR must keep `supernovacore.py` diff zero.
- If a legacy folder has launcher references, update or retire those launchers
  in a focused launcher-retirement PR before any source-folder deletion.
- If a legacy folder has deployment config, Dockerfiles, API routes, tests, or
  imports, treat it as deployment-sensitive and do a deeper audit first.
- Do not change FE7, backend route behavior, package files, lockfiles, secrets,
  env files, DB files, uploads, protocol docs, or deployment settings as part of
  legacy folder removal unless the PR explicitly scopes that change.

## Reference Checks Performed

Command shape used for this roadmap:

```powershell
rg -n --glob '!**/node_modules/**' --glob '!**/.next/**' --glob '!**/__pycache__/**' --glob '!**/.venv/**' --glob '!**/dist/**' --glob '!**/build/**' --glob '!**/*.log' --glob '!**/*.db' --glob '!**/package-lock.json' --glob '!**/*.tsbuildinfo' <legacy-folder-name> .
```

Additional checks:

- README and `REPO_STATUS.md` active-surface references.
- Package/deployment files including `package.json`, `Dockerfile`, `vercel.json`,
  `docker-compose.yml`, PowerShell launchers, and local launcher scripts.
- Tracked generated-artifact scan for `.next`, logs, local DB files, caches, and
  `tsconfig.tsbuildinfo`.

## Legacy Surface Inventory

| Legacy surface | Reference findings | Risk classification | Future cleanup direction |
| --- | --- | --- | --- |
| `super-nova-2177/frontend-nova` | Deleted after launcher retirement and fresh reference checks found no active package, deployment, workflow, or runtime references. `start_frontend_nova.ps1` was removed with the source folder. | Completed first explicit legacy source-folder deletion. | Roll back with a single revert if the retired source is needed again. |
| `super-nova-2177/frontend-professional` | Deleted after launcher retirement and fresh reference checks found no active package, deployment, workflow, runtime, or local launcher dependency. The unified launcher keeps only a retired/off-path handoff to Social Seven. | Completed explicit legacy source-folder deletion. | Roll back with a single revert if the retired source is needed again. |
| `super-nova-2177/frontend-next` | Source retained; runnable local launcher support retired after fresh checks. Dedicated deployment/auth/security audit found a standalone Next package, Dockerfile, Supabase auth dependencies, and an `app/api/ai` route. Local repo checks found no active workflow or external deploy config pointing to it, but Vercel/project-root settings were not manually verified. | Deployment/auth/security-sensitive legacy Next app; no active launcher. | Defer source deletion until manual Vercel/project-root verification confirms the folder, Dockerfile path, Supabase auth surface, and `/api/ai` handler are not deployed. |
| `super-nova-2177/frontend-social-six` | Source and launchers retained. Dedicated auth/deployment audit found a standalone Next package, Dockerfile, Supabase auth dependencies, `SOCIAL_AUTH_SETUP.md`, and an `app/api/ai` route. Local repo checks found no active workflow or external deploy config pointing to it, but Supabase/Vercel/Railway settings were not manually verified. | Auth-history-sensitive legacy social frontend with active local launcher. | Defer launcher retirement and source deletion until manual Supabase/Vercel/Railway verification confirms the provider-auth flow, Dockerfile path, and `/api/ai` handler are inactive. |
| `super-nova-2177/frontend-vite-basic` | Referenced by cleanup docs, launcher scripts, `scripts/check_safe.py`, and protected `frontend-vite-basic/supernovacore.py` zero-diff checks. | Protected-core-sensitive. | Do not touch in early cleanup; any removal needs a separate protected-core-safe plan. |
| `super-nova-2177/frontend-vite-3d` | Source retained; runnable local launcher support retired after fresh checks. Dedicated deployment/API audit found a standalone Vite package, `vercel.json`, and Vercel-style `api/` handlers. Local repo checks found no active workflow or external deploy config pointing to it, but Vercel project-root settings were not manually verified. | Deployment/API-sensitive; no active launcher. | Defer source deletion until manual Vercel/project-root verification confirms the folder and `/api/*` handlers are not deployed. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web` | Dedicated nested-surface audit found a standalone Next app with package/lock/config files, API stubs, app routes, and universe docs references. | Nested legacy app; dependency/security/deployment-sensitive. | Keep retained until manual deployment checks, dependency strategy, and universe UI preservation decisions are complete. See `NESTED_LEGACY_SURFACES_AUDIT.md`. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/nova-api` | Dedicated nested-surface audit found a small standalone FastAPI service with Dockerfile and sample `/api`, `/healthz`, and `/feed` routes. | Low visible reference count, but nested backend/deployment-sensitive. | Keep retained until manual deployment checks confirm no project root or Docker/Railway path uses it. See `NESTED_LEGACY_SURFACES_AUDIT.md`. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend` | Dedicated nested-surface audit found a NiceGUI/Python UI package with install scripts, compatibility wrappers, imports, docs, and many tests. | High cleanup risk legacy Python UI package. | Do not delete, rename, or move without an import/wrapper/test migration plan. See `NESTED_LEGACY_SURFACES_AUDIT.md`. |

## Generated Artifact Findings

Tracked generated candidates found in the roadmap assessment:

- `super-nova-2177/frontend-vite-3d/tsconfig.tsbuildinfo`
- `super-nova-2177/frontend-vite-basic/tsconfig.tsbuildinfo`

The follow-up generated-artifact cleanup removes these tracked files only. Root
`.gitignore` already contains `*.tsbuildinfo`, and active FE7 also has local
coverage, so TypeScript build-info artifacts should not be reintroduced.

## Recommended Cleanup Sequence

This alpha-readiness pass is documentation and label prep only. It keeps
`frontend-social-seven` as the only active/default frontend and does not delete
legacy source folders, package files, lockfiles, launcher scripts, or deployment
config.

1. Generated artifact cleanup PR: remove tracked `tsconfig.tsbuildinfo` files and
   confirm FE7 build, backend safe checks, and protected core diff zero.
2. `frontend-nova` launcher deprecation prep: completed.
3. `frontend-nova` launcher retirement PR: completed.
4. `frontend-nova` deletion PR: completed after fresh reference checks found no
   active package, deployment, workflow, or runtime references.
5. `frontend-professional` launcher retirement PR: completed.
6. `frontend-professional` deletion PR: completed after fresh reference checks
   found no active package, deployment, workflow, runtime, or local launcher
   dependency.
7. `frontend-vite-3d` launcher retirement PR: completed; source folder is still
   retained. Dedicated deployment/API audit is documented in
   `FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md`. A 2026-05-05 deletion gate recheck
   found no explicit external Vercel/DNS/env/manual-smoke evidence, so deletion
   remains deferred until manual verification proves it safe.
8. `frontend-next` launcher retirement PR: completed; source folder is still
   retained. Dedicated deployment/auth/security audit is documented in
   `FRONTEND_NEXT_DEPLOYMENT_AUDIT.md`, and deletion remains deferred until
   manual Vercel/project-root verification proves it safe.
9. `frontend-social-six` auth/deployment audit: completed; source folder and
   launchers are still retained. Audit is documented in
   `FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md`, and launcher retirement remains
   deferred until manual Supabase/Vercel/Railway verification proves it safe.
10. Nested legacy surfaces audit: completed. `nova-web`, `nova-api`, and
    `transcendental_resonance_frontend` remain retained; future cleanup requires
    the gates in `NESTED_LEGACY_SURFACES_AUDIT.md`.
11. Local Docker Compose audit: completed. Project-level
    `super-nova-2177/docker-compose.yml` remains unchanged and is treated as
    stale local-only because it still builds missing `./frontend`; see
    `LOCAL_DOCKER_COMPOSE_AUDIT.md` before changing or retiring Compose files.
12. Do not schedule `frontend-vite-basic` removal until the protected duplicate
   core file and safe-check contract have a dedicated plan.
13. Do not schedule `transcendental_resonance_frontend` removal until imports,
   tests, install scripts, and compatibility wrappers are intentionally retired.

## Required Checks Before Any Future Deletion

- `rg` references for the exact target folder name.
- README and `REPO_STATUS.md` review.
- Package/deployment review for package files, Dockerfiles, Vercel/Railway config,
  local launchers, scripts, and CI/workflows.
- FE7 lint/build.
- Backend safe checks.
- Live social/backend smoke when requested.
- Protected core diff zero.
- PR body with rollback plan and exact target list.

## Rollback

For this roadmap PR, rollback is a single revert restoring the prior cleanup docs
and ownership map.

For future deletion PRs, rollback must be a single revert that restores the
removed folder and any launcher/docs references changed in that same PR.
