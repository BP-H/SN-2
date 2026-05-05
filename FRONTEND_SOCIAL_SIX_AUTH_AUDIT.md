# frontend-social-six Auth/Deployment Audit

Date: 2026-05-05

## Decision

Deletion was performed in a later single-target cleanup PR. The owner explicitly
accepted the external Supabase/Vercel/Railway/auth/API-route risk documented
below, and fresh repo-local reference checks still found no active workflow,
package, launcher, script, or deployment config outside the folder pointing to
`super-nova-2177/frontend-social-six/`.

The deletion PR also removed `super-nova-2177/start_frontend_social_six.ps1`,
removed `social-six` from `run_local.py`, and changed the unified launcher
option 6 into a deleted/off-path handoff to Social Seven. It did not change
runtime behavior, frontend UI, backend routes, deployment settings, uploads, DB
files, Docker Compose behavior, or protected core.

## 2026-05-05 Owner-Accepted Deletion

The owner explicitly accepted the remaining external uncertainty:

- unknown Supabase provider redirect dependency
- unknown Vercel/Railway/Docker project-root state
- unknown active `app/api/ai` exposure
- unknown external auth/debug/manual QA dependency on Social Six

With that risk accepted, the tracked `super-nova-2177/frontend-social-six/`
source and launcher were deleted as a single cleanup target. Active production
remains `frontend-social-seven` only. Rollback is a single revert of the
deletion PR if the retired Social Six source, launcher, Dockerfile, Supabase
auth surface, or `app/api/ai` handler are needed again.

## Reference Checks Performed

- `git grep -n "frontend-social-six" -- .`
- `git grep -n "social-six" -- .`
- `git grep -n "start_frontend_social_six" -- .`
- Searched `.github/workflows`.
- Searched package files, Dockerfiles, compose files, Vercel/Railway files,
  scripts, launchers, JSON, and docs.
- Inspected `super-nova-2177/frontend-social-six/package.json`.
- Inspected `super-nova-2177/frontend-social-six/Dockerfile`.
- Inspected `super-nova-2177/frontend-social-six/next.config.mjs`.
- Inspected `super-nova-2177/frontend-social-six/SOCIAL_AUTH_SETUP.md`.
- Inspected `super-nova-2177/frontend-social-six/supabaseClient.js`.
- Inspected `super-nova-2177/frontend-social-six/app/api/ai/route.js`.
- Confirmed `run_local.py` exposed `social-six` before deletion.
- Confirmed `start_supernova.ps1` exposed `frontend-social-six` before deletion.

## Audit Result

Local repo checks found these references before deletion:

- Cleanup/status/security docs.
- `scripts/list_cleanup_candidates.py`, which keeps the source listed as a
  cleanup candidate.
- `super-nova-2177/run_local.py`.
- `super-nova-2177/start_supernova.ps1`.
- `super-nova-2177/start_frontend_social_six.ps1`.
- `super-nova-2177/frontend-social-six/SOCIAL_AUTH_SETUP.md`.
- `super-nova-2177/frontend-social-six/package.json`.

Fresh deletion checks found no active GitHub workflow or repo-level deployment
config outside `frontend-social-six/` pointing at this folder. Manual Vercel,
Railway, Docker, and Supabase dashboard settings were not verified; that risk
was explicitly accepted by the owner for deletion.

## Auth/Deployment Notes

`frontend-social-six` was auth/deployment-sensitive because it contained:

- A standalone Next package and lockfiles.
- A `Dockerfile`.
- Supabase auth dependencies and `supabaseClient.js`.
- `SOCIAL_AUTH_SETUP.md` with Google, Facebook, and GitHub provider setup and
  redirect URLs.
- A legacy social auth flow that imports provider profile names/photos.
- An `app/api/ai/route.js` handler that uses server-side `OPENAI_API_KEY`.

The auth setup appears historical/off-path relative to active FE7, but the repo
alone cannot prove no external auth provider or deployment still references it.
Deletion proceeded after the owner accepted that unresolved external risk.

## Current State

- Active/default frontend remains `super-nova-2177/frontend-social-seven`.
- Tracked `frontend-social-six` source was deleted.
- `frontend-social-six` no longer appears in `run_local.py --list-frontends`.
- `start_supernova.ps1` option 6 is a deleted/off-path handoff to Social Seven.
- `start_frontend_social_six.ps1` was removed.

## Historical Launcher Retirement Checklist

This was the preferred external verification checklist before the owner accepted
the risk and deletion proceeded:

- No Vercel project root points to `super-nova-2177/frontend-social-six`.
- No Railway/Docker deploy path uses `frontend-social-six/Dockerfile`.
- No Supabase provider redirect URL depends on the Social Six local or deployed
  URL as an active surface.
- No user-support or QA flow still needs the Social Six provider-auth path.
- FE7 remains the documented active/default frontend.

## Historical Source Deletion Checklist

Before deleting `frontend-social-six/`, the preferred checks also included:

- No active route depends on `frontend-social-six/app/api/ai/route.js`.
- No active auth migration/debugging process depends on
  `SOCIAL_AUTH_SETUP.md`.
- No CI/workflow/package script invokes this folder.
- FE7 lint/build, backend checks, cleanup guards, and protected-core zero-diff
  pass after deletion.

## Rollback

Rollback is a single revert restoring `super-nova-2177/frontend-social-six/`,
`super-nova-2177/start_frontend_social_six.ps1`, Social Six launcher entries,
the Dockerfile, Supabase auth surface, `app/api/ai` handler, and cleanup
candidate docs.
