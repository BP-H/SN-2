# frontend-social-six Auth/Deployment Audit

Date: 2026-05-05

## Decision

`super-nova-2177/frontend-social-six/` source is retained. Runnable local
launcher support is also retained for now. Launcher retirement and source deletion are deferred because the folder is auth-history-sensitive and external Supabase/Vercel/Railway project settings were not manually verified.

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
- Confirmed `run_local.py` still exposes `social-six`.
- Confirmed `start_supernova.ps1` still exposes `frontend-social-six`.

## Audit Result

Local repo checks found these references:

- Cleanup/status/security docs.
- `scripts/list_cleanup_candidates.py`, which keeps the source listed as a
  cleanup candidate.
- `super-nova-2177/run_local.py`.
- `super-nova-2177/start_supernova.ps1`.
- `super-nova-2177/start_frontend_social_six.ps1`.
- `super-nova-2177/frontend-social-six/SOCIAL_AUTH_SETUP.md`.
- `super-nova-2177/frontend-social-six/package.json`.

No active GitHub workflow or repo-level deployment config outside
`frontend-social-six/` was found pointing at this folder. Manual Vercel,
Railway, and Supabase dashboard settings were not verified.

## Auth/Deployment Notes

`frontend-social-six` is not safe for source deletion, and its launcher is not
retired in this PR, because it contains:

- A standalone Next package and lockfiles.
- A `Dockerfile`.
- Supabase auth dependencies and `supabaseClient.js`.
- `SOCIAL_AUTH_SETUP.md` with Google, Facebook, and GitHub provider setup and
  redirect URLs.
- A legacy social auth flow that imports provider profile names/photos.
- An `app/api/ai/route.js` handler that uses server-side `OPENAI_API_KEY`.

The auth setup appears historical/off-path relative to active FE7, but the repo
alone cannot prove no external auth provider or deployment still references it.

## Current State

- Active/default frontend remains `super-nova-2177/frontend-social-seven`.
- `frontend-social-six` source remains in the repo.
- `frontend-social-six` remains available in `run_local.py --list-frontends`.
- `start_supernova.ps1` option 6 still launches Social Six.
- `start_frontend_social_six.ps1` remains present.

## Future Launcher Retirement Checklist

Before retiring Social Six launchers, verify:

- No Vercel project root points to `super-nova-2177/frontend-social-six`.
- No Railway/Docker deploy path uses `frontend-social-six/Dockerfile`.
- No Supabase provider redirect URL depends on the Social Six local or deployed
  URL as an active surface.
- No user-support or QA flow still needs the Social Six provider-auth path.
- FE7 remains the documented active/default frontend.

## Future Source Deletion Checklist

Before deleting `frontend-social-six/`, also verify:

- No active route depends on `frontend-social-six/app/api/ai/route.js`.
- No active auth migration/debugging process depends on
  `SOCIAL_AUTH_SETUP.md`.
- No CI/workflow/package script invokes this folder.
- FE7 lint/build, backend checks, cleanup guards, and protected-core zero-diff
  pass after deletion.

## Rollback

This audit-only PR does not retire launchers or delete source. Rollback is a
single revert of the audit/status documentation and static guard updates.
