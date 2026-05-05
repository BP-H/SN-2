# Legacy Cleanup Roadmap

Branch: `cleanup/legacy-cleanup-roadmap`

Title: `[codex] Add legacy cleanup roadmap`

## Goal

Move toward one active frontend and one active backend without weakening the
SuperNova Core contract or changing production behavior.

This PR is documentation-first. It does not delete legacy source folders, change
runtime behavior, change deployment config, or edit protected core files.

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
| `super-nova-2177/frontend-professional` | Source retained; runnable launcher support retired after fresh checks. Remaining references are cleanup/status docs, `scripts/list_cleanup_candidates.py`, the retired `start_supernova.ps1` option text, and package self-references. | Source-retirement candidate; no active launcher. | Consider source deletion in a later single-target PR after another fresh package/deployment/workflow reference check. |
| `super-nova-2177/frontend-next` | Referenced by cleanup/security docs, `REPO_STATUS.md`, `run_local.py`, `start_supernova.ps1`, `start_frontend_next.ps1`, and `frontend-social-six` docs; has `Dockerfile` and package files. | Deployment/security-sensitive legacy Next app. | Do not delete until a legacy Next deployment assessment confirms it is unused. |
| `super-nova-2177/frontend-social-six` | Referenced by auth/security docs, cleanup docs, RSC/Next assessment, `REPO_STATUS.md`, launchers, `Dockerfile`, and social auth setup docs. | Auth-history-sensitive legacy social frontend. | Defer until a dedicated social-six retirement assessment. |
| `super-nova-2177/frontend-vite-basic` | Referenced by cleanup docs, launcher scripts, `scripts/check_safe.py`, and protected `frontend-vite-basic/supernovacore.py` zero-diff checks. | Protected-core-sensitive. | Do not touch in early cleanup; any removal needs a separate protected-core-safe plan. |
| `super-nova-2177/frontend-vite-3d` | Referenced by cleanup docs, `REPO_STATUS.md`, launchers, `package.json`, and its own `vercel.json`; prior assessment notes Vercel-style API routes. | Deployment-sensitive. | Defer until deployment/API route audit. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web` | Referenced by nested cleanup/security docs, `REPO_STATUS.md`, package/lockfile files, Next config, internal comments, and universe docs. | Nested legacy app and dependency-sensitive. | Keep under nested backend/lockfile cleanup plan. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/nova-api` | Referenced by `REPO_STATUS.md` and its own `index.py`. | Low visible reference count, but nested backend-sensitive. | Assess with nested backend cleanup, not frontend cleanup. |
| `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend` | Referenced by `REPO_STATUS.md`, many nested docs, install scripts, utility imports, compatibility wrappers, and tests. | Do not touch. Active legacy Python UI package. | Do not delete or rename without a compatibility and test audit. |

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
5. `frontend-professional` launcher retirement PR: completed; source folder is
   still retained for a later explicit deletion PR.
6. Repeat the source deletion pattern for `frontend-professional` only after a
   fresh reference check confirms no active package, deployment, workflow, or
   runtime dependency.
7. Separate assessments for `frontend-next`, `frontend-social-six`,
   `frontend-vite-3d`, nested `nova-web`, and nested `nova-api`.
8. Do not schedule `frontend-vite-basic` removal until the protected duplicate
   core file and safe-check contract have a dedicated plan.
9. Do not schedule `transcendental_resonance_frontend` removal until imports,
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
