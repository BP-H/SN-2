# frontend-next Deployment/Auth Audit

Date: 2026-05-05

## Decision

`super-nova-2177/frontend-next/` source is retained. Runnable local launcher
support is retired because local reference checks found no active workflow,
deployment config, or repo-level runtime dependency outside docs and local
launchers. Source deletion is deferred because the folder is
deployment/auth/security-sensitive.

## Reference Checks Performed

- `git grep -n "frontend-next" -- .`
- `git grep -n "start_frontend_next" -- .`
- Searched `.github/workflows`.
- Searched package files, Dockerfiles, compose files, Vercel/Railway files,
  scripts, launchers, JSON, and docs.
- Inspected `super-nova-2177/frontend-next/package.json`.
- Inspected `super-nova-2177/frontend-next/Dockerfile`.
- Inspected `super-nova-2177/frontend-next/next.config.mjs`.
- Inspected `super-nova-2177/frontend-next/app/api/ai/route.js`.
- Confirmed `run_local.py` exposed `next` before this retirement.
- Confirmed `start_supernova.ps1` exposed `frontend-next` before this
  retirement.

## Audit Result

Local repo checks found these references before retirement:

- Cleanup/status/security docs.
- `scripts/list_cleanup_candidates.py`, which keeps the source listed as a
  cleanup candidate.
- `super-nova-2177/run_local.py`.
- `super-nova-2177/start_supernova.ps1`.
- `super-nova-2177/start_frontend_next.ps1`.
- `super-nova-2177/frontend-social-six/SOCIAL_AUTH_SETUP.md`, which documents
  social-six as derived from the original Next app.

No active GitHub workflow or repo-level deploy config outside
`frontend-next/` was found pointing at this folder. Manual Vercel/Railway
project settings were not verified.

## Deployment/Auth/Security Notes

`frontend-next` is not safe for source deletion yet because it contains:

- A standalone Next package and lockfiles.
- A `Dockerfile`.
- Supabase auth dependencies and `supabaseClient.js`.
- An `app/api/ai/route.js` handler that uses server-side `OPENAI_API_KEY`.
- Legacy content and proposal routes that may be useful for future archaeology.

Deletion is deferred until manual Vercel/project-root verification confirms the
folder, Dockerfile path, Supabase auth surface, and `/api/ai` handler are not
deployed.

## Current State

- Active/default frontend remains `super-nova-2177/frontend-social-seven`.
- `frontend-next` source remains in the repo.
- `frontend-next` no longer appears in `run_local.py --list-frontends`.
- `start_supernova.ps1` option 1 is a retired handoff to Social Seven.
- `start_frontend_next.ps1` was removed.

## Future Deletion Checklist

Before deleting `frontend-next/`, verify:

- No Vercel project root points to `super-nova-2177/frontend-next`.
- No Railway/Docker deploy path uses `frontend-next/Dockerfile`.
- No production/staging auth settings depend on this app's Supabase client.
- No active route depends on `frontend-next/app/api/ai/route.js`.
- No CI/workflow/package script invokes this folder.
- FE7 lint/build, backend checks, cleanup guards, and protected-core zero-diff
  pass after deletion.

## Rollback

If the retired launcher is needed again, revert the launcher-retirement PR to
restore `start_frontend_next.ps1` and the `frontend-next` entries in
`run_local.py` and `start_supernova.ps1`.
