# frontend-vite-3d Deployment/API Audit

Date: 2026-05-05

## Decision

Deletion is deferred. `super-nova-2177/frontend-vite-3d/` remains in the tree as
a deployment-sensitive legacy source folder until a manual Vercel/project-root
verification confirms it is not deployed and its API routes are not live.

This PR is audit-only for the source folder. It does not change runtime
behavior, frontend UI, backend routes, deployment settings, uploads, DB files,
or protected core.

## 2026-05-05 Deletion Gate Recheck

Deletion remains blocked. The prompt and repository do not contain explicit
manual external deployment verification proving that `frontend-vite-3d` is safe
to delete.

Repo-local checks were repeated:

- `git grep -n "frontend-vite-3d" -- .`
- `git grep -n "vite-3d" -- .`
- `.github/workflows` search
- Vercel/Railway/Docker/Compose/deployment-file search
- package-file and lockfile search
- script and launcher search
- docs/status-file search
- `python super-nova-2177/run_local.py --list-frontends`
- `start_supernova.ps1` inspection
- `frontend-vite-3d/vercel.json` inspection
- `frontend-vite-3d/api/` inspection

Current repo-local findings:

- `run_local.py --list-frontends` no longer exposes `vite-3d`.
- `start_supernova.ps1` option 3 is a retired handoff to Social Seven.
- No GitHub Actions workflow points to `frontend-vite-3d`.
- No deployment config outside the retained folder points to
  `frontend-vite-3d`.
- The retained folder still contains `vercel.json`, `package.json`,
  `package-lock.json`, and Vercel-style `api/` handlers.
- Remaining references outside the retained folder are cleanup/status docs,
  static cleanup tests, and retired-launcher handoff text.

Missing external verification:

- No Vercel dashboard/API evidence proves that no active project root points to
  `super-nova-2177/frontend-vite-3d`.
- No Vercel dashboard/API evidence proves that no active deployment exposes its
  `/api/*` handlers.
- No DNS/domain evidence proves that no domain points at a deployment built from
  this folder.
- No environment-variable audit proves that no env var set exists solely for
  the folder's OpenAI helper endpoints.
- No external smoke/manual QA evidence proves that no flow depends on the Vite
  3D app or its API routes.

Result: do not delete `super-nova-2177/frontend-vite-3d/` yet. A later deletion
PR must include the missing external evidence above, then rerun fresh repo
reference checks and safety checks.

## Local Reference Checks

Required checks performed:

- `git grep -n "frontend-vite-3d" -- .`
- `git grep -n "vite-3d" -- .`
- `.github/workflows` search
- package, lockfile, Docker, compose, Vercel, Railway, and workflow-file search
- script/launcher/doc search
- `python super-nova-2177/run_local.py --list-frontends`
- `python scripts/list_cleanup_candidates.py`

Findings:

- `run_local.py` no longer exposes `vite-3d`.
- `start_supernova.ps1` only keeps a retired handoff message for option 3.
- `start_frontend_vite_3d.ps1` is gone.
- No GitHub Actions workflow points to `frontend-vite-3d`.
- No deployment config outside the retained folder points to `frontend-vite-3d`.
- The cleanup inventory still lists `frontend-vite-3d` as a retained legacy
  frontend cleanup candidate.
- Remaining repo references are cleanup/status docs, the cleanup unittest, the
  retired launcher handoff text, and source self-references inside the retained
  folder.

## package.json Audit

`super-nova-2177/frontend-vite-3d/package.json` is a private Vite app with:

- `dev`, `build`, `preview`, and `test` scripts.
- Node engine `>=20.17.0`.
- Three.js/React Three dependencies.
- `@google/genai`.
- `@vercel/node` in dev dependencies.

This is not referenced by active FE7 or current GitHub workflows, but it is a
complete standalone frontend package.

## vercel.json Audit

`super-nova-2177/frontend-vite-3d/vercel.json` contains:

- `buildCommand`: `npm run build`
- `outputDirectory`: `dist`
- `framework`: `vite`
- a SPA rewrite to `/index.html`

No checked-in `.vercel/project.json` was found during local file search, and no
workflow references this folder. However, local repository checks cannot prove
that no Vercel project is manually configured with this folder as its root.

## api/ Audit

`super-nova-2177/frontend-vite-3d/api/` contains Vercel-style serverless route
files:

- `assist.ts`: Edge runtime endpoint calling OpenAI Responses with server
  `OPENAI_API_KEY`.
- `assistant-reply.ts`: Vercel Node endpoint; production uses server
  `OPENAI_API_KEY`, while local/dev accepts `body.apiKey` fallback.
- `openai-ping.ts`: endpoint that requires an `apiKey` in the request body.
- `openai-quick-chat.ts`: endpoint that requires an `apiKey` in the request
  body.
- `players.ts`: simple read-only static player list endpoint.

These routes are not part of active FE7 and are not registered in the active
backend. They are still deployment-sensitive because they would be live if a
Vercel project uses `frontend-vite-3d` as its project root.

## Deletion Checklist

Before deleting `frontend-vite-3d`, verify all of the following:

1. In Vercel dashboard/API, no active project has `super-nova-2177/frontend-vite-3d`
   as its root directory.
2. No active Vercel deployment exposes the folder's `/api/*` handlers.
3. No DNS/domain points at a Vercel project built from this folder.
4. No environment variable set exists solely for this folder's OpenAI helper
   endpoints.
5. No external smoke/manual QA route depends on its Vite app or API routes.
6. Fresh repo checks still show no workflow, package, launcher, script, or
   deployment config outside the folder pointing to it.
7. Active FE7 lint/build and protected-core zero-diff pass after deletion.

## Rollback

For this audit-only PR, rollback is a single revert of documentation/test
changes. If a later deletion PR removes the source folder, rollback should be a
single revert restoring `super-nova-2177/frontend-vite-3d/` and the cleanup
candidate docs.
