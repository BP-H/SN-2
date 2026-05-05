# Cleanup Candidates Snapshot

Originally generated on 2026-04-26 from:

```powershell
python scripts/list_cleanup_candidates.py
```

This is a read-only inventory, later updated with explicit audit outcomes. It is
not approval to delete anything from `master`. Any cleanup should happen on a
separate branch, one candidate class at a time, with backend safety tests, FE7
lint/build, public protocol smoke, and protected-core zero diff.

Current checkpoint: `CLEANUP_STABILITY_CHECKPOINT.md` summarizes completed
cleanup, deferred cleanup, manual external verification needs, and the
recommended non-cleanup priorities before any further deletion work.

## Completed Cleanup

Completed entries are history, not active cleanup candidates.

- `super-nova-2177/backend/supernova_2177_ui_weighted/combined_repo.md` was removed in PR #9.
- It was a generated combined repository snapshot only.
- Reference search found no runtime imports or deployment references.
- Full checks passed before merge.
- Four tracked backup Python files were removed in PR #10 after reference checks and full safety checks.
- `super-nova-2177/frontend-nova` was deleted after launcher retirement and
  fresh reference checks found no active package, deployment, workflow, or
  runtime references.
- `super-nova-2177/frontend-professional` was deleted after fresh reference
  checks found no active package, deployment, workflow, runtime, or local
  launcher dependency.
- `super-nova-2177/frontend-vite-3d` runnable local launcher support was
  retired; the source folder remains a deployment-sensitive cleanup candidate
  until manual Vercel/project-root verification proves its Vite app and
  Vercel-style `/api/*` handlers are not deployed. The local repo audit is
  recorded in `FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md`. A 2026-05-05 deletion
  gate recheck found no explicit external Vercel/DNS/env/manual-smoke evidence,
  so deletion remains blocked.
- `super-nova-2177/frontend-next` runnable local launcher support was retired;
  the source folder remains a deployment/auth/security-sensitive cleanup
  candidate until manual Vercel/project-root verification proves its Next app,
  Dockerfile path, Supabase auth dependencies, and `/api/ai` handler are not
  deployed. The local repo audit is recorded in
  `FRONTEND_NEXT_DEPLOYMENT_AUDIT.md`.
- `super-nova-2177/frontend-social-six` was audited as auth-history-sensitive;
  source and runnable local launcher support remain intact until manual
  Supabase/Vercel/Railway verification proves its provider-auth flow,
  Dockerfile path, and `/api/ai` handler are inactive. The local repo audit is
  recorded in `FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md`.

## Legacy Or Experimental Frontend Trees

These folders are retained/deferred candidates. Deleted folders such as
`frontend-nova` and `frontend-professional` should not be relisted here.

- `super-nova-2177/frontend-next`
- `super-nova-2177/frontend-social-six`
- `super-nova-2177/frontend-vite-3d`
- `super-nova-2177/frontend-vite-basic`

## Nested Backend Experiments

- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/Dockerfile`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/__init__.py`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/app.py`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/requirements.txt`

Nested legacy surfaces under `backend/supernova_2177_ui_weighted/` were audited
in `NESTED_LEGACY_SURFACES_AUDIT.md`. `nova-web`, `nova-api`, and
`transcendental_resonance_frontend` remain retained; deletion is deferred until
deployment/import/test gates are satisfied.

## Local Docker Compose Config

- `super-nova-2177/docker-compose.yml` remains unchanged after the audit in
  `LOCAL_DOCKER_COMPOSE_AUDIT.md`. Its frontend service still builds missing
  `./frontend`, so it is treated as stale local-only until a dedicated Docker
  smoke/update or retirement PR.
- `super-nova-2177/backend/supernova_2177_ui_weighted/docker-compose.yml`
  remains retained under `NESTED_LEGACY_SURFACES_AUDIT.md` gates.
- `super-nova-2177/backend/supernova_2177_ui_weighted/backend/docker-compose.yml`
  remains retained under `NESTED_LEGACY_SURFACES_AUDIT.md` gates.

## Node Lockfiles Inside Backend Or Module Trees

- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web/package-lock.json`
- `super-nova-2177/backend/supernova_2177_ui_weighted/package-lock.json`

## Tracked Uploads

- `super-nova-2177/backend/uploads/1bb86e27e1c741b08274c4753f393777`
- `super-nova-2177/backend/uploads/380fa79e48e847f7a83acf32f7b424cb`
- `super-nova-2177/backend/uploads/4f7003858bbd41a89a17743a562543f0`

## Typo-Named Tracked Files

- `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend/tr_pages/animate_gaussion.py`
- `super-nova-2177/frontend-next/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-social-seven/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-social-six/content/proposal/content/LikesDeslikes.jsx`
- `super-nova-2177/frontend-vite-3d/src/components/LikesDeslikes.tsx`
- `super-nova-2177/frontend-vite-basic/src/components/LikesDeslikes.tsx`

## Cleanup Rule

Review these on a separate cleanup branch before deleting or renaming anything.
