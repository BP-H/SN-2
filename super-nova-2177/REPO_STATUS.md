# SuperNova 2177 Repo Status

This file is the current safety map for the repo. It is intentionally documentation-only: do not move or delete folders just to clean the tree while production is live.

## Active Online Surfaces

- Backend API: `backend/app.py`
- Railway compatibility entrypoint: `app.py`, which imports `backend.app:app`
- Active social frontend: `frontend-social-seven`
- Frontend API env var: `NEXT_PUBLIC_API_URL`
- Backend production DB env var: `DATABASE_URL`
- SuperNova Core source: `backend/supernova_2177_ui_weighted/supernovacore.py`
- Core gateway mount: backend exposes future core routes under `/core/...`
- Root GitHub README: `../README.md`
- Fork manifest: `universe.fork.json`

## Active Local Surfaces

- Local launcher: `run_local.py`
- Local frontend seven port: `3007`
- Local backend port: `8000`
- Preserved local social DB: `supernova_local.db`

When `DATABASE_URL` is not set locally, the backend wrapper should use `supernova_local.db` instead of creating a fresh `universe_*.db` for the social feed.

## Legacy Or Experimental Surfaces

These folders may contain useful experiments, references, or older frontend variants, but they are not the primary production path right now.

- `frontend-social-six` (source and launcher retained pending auth/deployment verification)
- `frontend-next` (source retained; local launcher retired pending deployment/auth/security audit)
- `frontend-vite-basic`
- `frontend-vite-3d`
- `backend/supernova_2177_ui_weighted/nova-web`
- `backend/supernova_2177_ui_weighted/nova-api`
- `backend/supernova_2177_ui_weighted/transcendental_resonance_frontend`
- Root `docker-compose.yml` frontend service, which references an older `./frontend` path and should be treated as local legacy until updated deliberately.

## Cleanup Policy

- The only active/default frontend is `frontend-social-seven`.
- The active backend is `backend/app.py`.
- The Railway compatibility entrypoint is `app.py`.
- Local launchers should keep `frontend-social-seven` as the active/default FE7 path. `frontend-nova` and `frontend-professional` were deleted after launcher retirement and fresh reference checks; restore either only by reverting its deletion PR. `frontend-vite-3d` source is still present, but its runnable local launcher support has been retired. Its deployment/API-route audit is documented in `../FRONTEND_VITE_3D_DEPLOYMENT_AUDIT.md`. `frontend-next` source is still present, but its runnable local launcher support has been retired pending deployment/auth/security verification documented in `../FRONTEND_NEXT_DEPLOYMENT_AUDIT.md`. `frontend-social-six` source and launcher support remain intact pending auth/deployment verification documented in `../FRONTEND_SOCIAL_SIX_AUTH_AUDIT.md`.
- All other top-level frontend folders are legacy/off-path unless a future PR explicitly promotes one after reference, package, and deployment checks.
- `backend/supernova_2177_ui_weighted/supernovacore.py` is protected core. Do not edit, move, rename, delete, reformat, or copy its logic during cleanup.
- Legacy folders are eligible for staged cleanup only after reference checks for package files, deployment config, Dockerfiles, README/docs, scripts, imports, and CI/workflows.
- Do not delete legacy source folders in broad mixed cleanup PRs. Prefer one target folder or one generated-artifact class per deletion PR.
- If a legacy folder is referenced by local launchers, update or retire those launcher references in the same explicit cleanup PR before deletion.
- If a legacy folder contains deployment config, API routes, Dockerfiles, tests, or protected-core-like files, treat it as deployment-sensitive until a deeper audit proves otherwise.
- Keep protocol docs/routes active where currently used. Do not classify protocol files as legacy frontend cleanup.
- Keep `NEXT_PUBLIC_API_URL` and `DATABASE_URL` as the active frontend/backend env var names.

## Legacy Classification Rules

- Do not move active deployment paths while Railway/Vercel are live: `app.py`, `backend/app.py`, and `frontend-social-seven`.
- Treat files with names like `* copy.jsx`, backup pages, bundled demos, and old Vite/Next experiments as reference material unless a task explicitly promotes them.
- Treat `*.db`, `*.log`, `uploads/`, `.next/`, and local JSON fallback stores as local state, not source. They are ignored and should not be used to judge production history.
- If a legacy experiment contains a visual or logic idea worth keeping, port the smallest stable piece into the active frontend/backend instead of changing deployment roots.

## Species Contract

SuperNova has exactly three species keys in the social wrapper and frontend seven:

- `human`
- `ai`
- `company`

Silent browser sync must not overwrite an existing account species. Explicit profile updates may change species. Proposal creation, proposal votes, system votes, and comments should prefer the saved backend account species when a known user exists.

## Deployment Safety Notes

- Do not edit `supernovacore.py` for wrapper or frontend connectivity fixes unless a task explicitly asks for core changes.
- Keep existing social endpoints stable: `/proposals`, `/votes`, `/comments`, `/profile`, `/messages`, `/follows`, `/auth/...`.
- Keep feed reads bounded. `/proposals` supports `limit`, `offset`, `before_id`, and `author`; frontend seven should request small slices instead of loading the whole feed.
- Keep graph reads bounded. `/social-graph` should sample recent proposals, comments, votes, messages, and follows rather than scanning whole tables.
- Link rendering belongs in frontend presentation helpers; backend should keep storing plain text unless a dedicated rich-text contract is added.
- Add new core-backed frontend features through `API_BASE_URL + "/core/..."`.
- Keep `universe.fork.json` documentation-only until deliberate fork tooling is added.
- Railway should provide `DATABASE_URL`; the runtime wrapper preserves that and does not force local SQLite in production.
- Vercel should set `NEXT_PUBLIC_API_URL` to the Railway backend URL without a trailing slash.
- Public API CORS is intentionally open by default for federation-style, non-cookie access. Keep `allow_credentials=false`; protect identity with bearer tokens, domain verification, and future signatures rather than origin lock-in.
- Only set `ALLOWED_ORIGINS` or `BACKEND_ALLOWED_ORIGINS` when deliberately running a private/allowlisted surface. `/health` and `/supernova-status` report the active federation/CORS mode.
- Read-only federation surfaces are additive and safe to disable by routing if needed: `/.well-known/supernova`, `/.well-known/webfinger`, `/actors/{username}`, `/actors/{username}/outbox`, and `/u/{username}/export.json`.
- Federation profile payloads distinguish claimed domains from verified domains. Until ownership proof is implemented, `domain_verified` stays false and no verified-domain badge should be shown.
