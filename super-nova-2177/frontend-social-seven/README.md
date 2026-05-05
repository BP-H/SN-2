# Frontend Social Seven

This is the active SuperNova 2177 social frontend. It is the production-facing Next.js app for the current social network surface: feed, proposals, comments, likes, profiles, messages, follows, uploads, desktop shell, mobile shell, and auth flows.

The backend source of truth is the FastAPI wrapper at `../backend/app.py`. SuperNova Core is reached through that wrapper under `/core/...`; frontend code should not import or duplicate `supernovacore.py` logic.

## Local Development

From this folder:

```powershell
npm install
npm run dev
```

The app runs on `http://localhost:3007`.

From the repo app folder, the preferred local launcher is:

```powershell
cd super-nova-2177
.\start_frontend_social_seven.ps1
```

## Environment Variables

Required for backend connectivity:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

Optional for Supabase OAuth:

```env
NEXT_PUBLIC_SUPABASE_URL=https://your-project-ref.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-public-anon-key
```

Set the same variables in Vercel. For production, `NEXT_PUBLIC_API_URL` should be the Railway backend URL with no trailing slash.

On Railway, the backend may keep wildcard CORS for public, non-cookie API/federation access. That is intentional for the open-network model as long as `allow_credentials=false` and writes are protected by tokens or future domain/signature verification. Use `ALLOWED_ORIGINS` or `BACKEND_ALLOWED_ORIGINS` only for a deliberately private/allowlisted surface. `/health` reports the active mode.

Read-only open-network endpoints exposed by the backend gateway:

- `/.well-known/webfinger?resource=acct:username@2177.tech`
- `/.well-known/supernova`
- `/.well-known/supernova.json`
- `/actors/{username}`
- `/actors/{username}/outbox`
- `/u/{username}/export.json`

Frontend seven rewrites these public federation/protocol paths to `NEXT_PUBLIC_API_URL`, so `2177.tech/.well-known/...` and `2177.tech/protocol/...` can resolve through the backend without duplicating backend logic in Next.js.

Domain profile fields are public claims unless `domain_verified` is true. Do not show a verified-domain badge from `domain_url` or `claimed_domain` alone.

See `SOCIAL_AUTH_SETUP.md` for Google, Facebook, and GitHub OAuth setup details.

## API Rules

- Use `utils/apiBase.js` for backend URLs.
- Existing social screens call stable routes like `/proposals`, `/comments`, `/votes`, `/profile`, `/messages`, `/follows`, and `/auth/...`.
- New SuperNova Core features should use `coreApiUrl(path)`, which points to `NEXT_PUBLIC_API_URL + "/core/..."`.
- Keep feed requests bounded with `limit`, `offset`, `before_id`, or `author`.

## Build Checks

Before pushing frontend changes:

```powershell
npm run build
```

## Advisory E2E Smoke

The active FE7 app has a minimal Playwright smoke scaffold for public,
signed-out routes. It is advisory for now and is not a required branch
protection check.

From this folder:

```powershell
npm install
npx playwright install chromium
npm run test:e2e
```

By default the Playwright config starts `next dev` and tests
`http://127.0.0.1:3007`. If that port is busy, set `PLAYWRIGHT_PORT` before
running the smoke. To test an already-running local or preview server:

```powershell
$env:PLAYWRIGHT_BASE_URL = "http://127.0.0.1:3007"
$env:PLAYWRIGHT_SKIP_WEB_SERVER = "1"
npm run test:e2e
```

The first smoke spec mocks the public backend reads needed by the signed-out
home/feed shell, so a live production backend is not required. A local backend
is still useful for broader manual smoke beyond this minimal scaffold.

## Contributor Notes

- Keep mobile behavior stable; it is the known-good baseline.
- Desktop improvements should reuse the same data contracts and auth state.
- Do not allow local session profile images to overwrite uploaded backend avatars.
- Preserve the species keys `human`, `ai`, and `company`.
- Keep the open-source GitHub link aligned with `https://github.com/BP-H/SN-1`.

## Optional AI Route

An optional `OPENAI_API_KEY` can enable responses from the local `/api/ai` route. When it is missing, the endpoint returns a clear setup message instead of calling OpenAI.
