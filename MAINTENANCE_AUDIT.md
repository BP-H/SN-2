# Maintenance Audit

This audit captures cleanup direction without changing runtime behavior. Do not delete or refactor live paths from `master` just because they appear here. Use a separate branch and prove each change with tests first.

## Active Production Paths

- `app.py`: Railway/root compatibility entrypoint.
- `super-nova-2177/backend/app.py`: active FastAPI wrapper, public protocol routes, and FE7 social API surface.
- `super-nova-2177/frontend-social-seven/`: active FE7 web frontend.
- `super-nova-2177/protocol/`: canonical public protocol schemas and examples.
- `super-nova-2177/backend/protocol/`: backend-deploy mirror of public protocol schemas and examples.
- `scripts/smoke_protocol.py`: public protocol smoke check.
- `DEPLOYMENT_SMOKE_CHECK.md`: manual deployment verification checklist.

## Protected Core Paths

- `super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py`
- `super-nova-2177/frontend-vite-basic/supernovacore.py`

Do not edit these for wrapper, FE7, deployment, protocol-doc, or smoke-check work unless the task explicitly asks for core changes.

## Stable Social Routes

Keep these compatible unless a dedicated migration plan exists:

- `/proposals`
- `/votes`
- `/comments`
- `/profile`
- `/messages`
- `/follows`
- `/auth/...`

## Legacy Or Experimental Candidates

These may be useful references or future branches, but should not be deleted from `master` without branch-tested proof:

- `super-nova-2177/frontend-next/`
- `super-nova-2177/frontend-social-six/`
- `super-nova-2177/frontend-vite-3d/`
- `super-nova-2177/frontend-vite-basic/`
- nested or duplicate backend experiments under `super-nova-2177/backend/supernova_2177_ui_weighted/`

`super-nova-2177/frontend-nova/` was deleted after its local launchers were
retired and fresh reference checks confirmed no active package, deployment,
workflow, or runtime dependency.

`super-nova-2177/frontend-professional/` was deleted after its runnable local
launcher paths were retired and fresh reference checks confirmed no active
package, deployment, workflow, runtime, or local launcher dependency.

`super-nova-2177/frontend-next/` remains in the tree because it has a standalone
Next package, Dockerfile, Supabase dependencies, and an `app/api/ai` route. Its
runnable local launcher paths were retired pending deployment/auth/security
verification. The audit is captured in `FRONTEND_NEXT_DEPLOYMENT_AUDIT.md`;
source deletion remains deferred until manual Vercel/project-root verification
confirms it is not deployed.

`super-nova-2177/frontend-vite-3d/` remains in the tree because it has package
self-references, its own `vercel.json`, and prior API-route/deployment notes.
Its runnable local launcher paths were retired pending a dedicated deployment
and API-route audit. The audit is now captured in
`FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md`; source deletion remains deferred until
manual Vercel/project-root verification confirms the folder's app and `/api/*`
handlers are not deployed.

## Generated Or Local Artifact Candidates

These should stay ignored where possible. If already tracked, remove only in a separate cleanup branch after confirming production and local workflows do not depend on them.

- `*.db`, `*.sqlite`, `*.sqlite3`
- `*.log`
- `.next/`, `dist/`, `build/`, `.cache/`
- `uploads/`
- `combined_repo.md`
- `*.bak`, `*.backup*`
- local message/follow stores

## Future Cleanup Branch Rules

1. Create a branch such as `cleanup/repo-hygiene-audit`.
2. Do not touch `supernovacore.py` unless the cleanup explicitly targets core.
3. Remove one class of artifact at a time.
4. Run backend federation tests, FE7 lint/build, and `scripts/smoke_protocol.py https://2177.tech`.
5. Keep public federation read-only and manual-preview-only.
6. Do not introduce automatic execution, company webhooks, ActivityPub inbox writes, Webmention fetching, or real domain verification fetching during cleanup.

For a read-only starting point, run `python scripts/list_cleanup_candidates.py`. It prints tracked cleanup candidates and never deletes files. The latest captured inventory is `CLEANUP_CANDIDATES_SNAPSHOT.md`.
