# Cleanup Stability Checkpoint

Date: 2026-05-05

## Decision

Pause broad cleanup. The repo has completed enough cleanup and audit work for
now; the next safe sprint should focus on alpha smoke evidence, branch
protection, smoke-blocker fixes, first-user polish, and durable media storage.

This checkpoint began as documentation-only. Later cleanup PRs may update this
status record after single-target cleanup work passes its own checks.

## Completed Cleanup

- `frontend-nova` was deleted after launcher retirement and fresh reference
  checks found no active package, deployment, workflow, or runtime dependency.
- `frontend-professional` launcher support was retired and the source folder was
  deleted after fresh reference checks found no active package, deployment,
  workflow, runtime, or local launcher dependency.
- `frontend-vite-3d` runnable local launcher support was retired, and the
  source folder was later deleted after fresh repo-local checks with
  owner-accepted external Vercel/API-route risk.
- `frontend-next` runnable local launcher support was retired. The source
  folder is retained pending deployment, auth, and security verification.
- `frontend-social-six` was audited only. Source and launcher support remain
  retained pending Supabase, Vercel, and Railway verification.
- Nested legacy surfaces under
  `backend/supernova_2177_ui_weighted/` were audited only. `nova-web`,
  `nova-api`, and `transcendental_resonance_frontend` remain retained pending
  deployment, import, and test gates.

## Still Retained

Do not touch these casually:

- Active FE7: `super-nova-2177/frontend-social-seven`
- Active backend: `super-nova-2177/backend/app.py`
- Protected core:
  `super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py`
- Protected duplicate core:
  `super-nova-2177/frontend-vite-basic/supernovacore.py`
- `super-nova-2177/frontend-vite-basic`
- `super-nova-2177/frontend-social-six`
- `super-nova-2177/frontend-next`
- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-web`
- `super-nova-2177/backend/supernova_2177_ui_weighted/nova-api`
- `super-nova-2177/backend/supernova_2177_ui_weighted/transcendental_resonance_frontend`

## Manual External Verification Needed

The local repo cannot prove these external states. Verify them manually before
future deletion or deployment-sensitive cleanup:

- Vercel project roots for `frontend-next` and possibly `frontend-social-six`;
  `frontend-vite-3d` external Vercel/API-route risk was explicitly accepted for
  deletion.
- Railway and Docker deploy roots
- Supabase provider redirect URLs for Social Six
- DNS and domain targets
- Durable media storage and old uploaded image bytes
- GitHub branch protection required checks
- Local Docker Compose and Docker deploy roots, especially stale `./frontend`
  references documented in `LOCAL_DOCKER_COMPOSE_AUDIT.md`

## Recommended Next Non-Cleanup Priorities

1. Complete manual alpha browser smoke and signoff.
2. Enable branch protection manually with:
   - `Backend local deterministic checks`
   - `FE7 local deterministic checks`
3. Fix only confirmed smoke blockers.
4. Run product/UI polish for the first-user experience.
5. Add durable object storage or equivalent for media.
6. Broaden E2E only after smoke stabilizes.

## Deferred Cleanup

- `frontend-vite-3d` has been deleted. Revert the deletion PR if the retired
  source or Vercel-style `/api/*` handlers are needed again.
- Do not delete `frontend-next` until Vercel/Railway/Docker project-root,
  Supabase auth, and `app/api/ai` exposure are manually checked.
- Do not retire or delete `frontend-social-six` until Supabase provider
  redirects, Vercel/Railway roots, and auth-history needs are manually checked.
- Do not move, rename, or delete nested legacy surfaces until deployment,
  import, wrapper, install-script, and test gates are satisfied.
- Do not update or retire local Docker Compose config until the manual checks in
  `LOCAL_DOCKER_COMPOSE_AUDIT.md` are complete.
- Do not touch protected core unless a future PR explicitly follows
  `CORE_CHANGE_PROTOCOL.md`.

## Rollback

Rollback for this checkpoint document is a single revert of its documentation
and static test changes. Runtime state, deployment settings, databases, upload
files, and protected core remain outside this checkpoint.
