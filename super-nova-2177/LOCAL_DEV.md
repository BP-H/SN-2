# Local Development

## Quick start

Run the backend and choose a frontend interactively:

```bash
python run_local.py
```

List the available frontend targets:

```bash
python run_local.py --list-frontends
```

Run only the backend:

```bash
python run_local.py --backend-only
```

Start a specific frontend:

```bash
python run_local.py --frontend vite-basic
python run_local.py --frontend social-seven
```

## What the launcher does

- Starts the FastAPI backend on `http://127.0.0.1:8000`
- Writes the correct local API URL into the selected frontend's `.env.local`
- Starts the selected frontend on its assigned local port

## Default local ports

- `backend`: `8000`
- `vite-basic`: `5174`
- `social-seven`: `3007`

`frontend-nova`, `frontend-professional`, `frontend-vite-3d`, `frontend-next`,
and `frontend-social-six` local launcher targets are retired/off-path. Use
`social-seven` for the active frontend. The `frontend-vite-3d` source folder was
deleted after retirement with owner-accepted external Vercel/API-route risk.
The tracked `frontend-next` source folder was deleted after retirement with
owner-accepted external deployment/auth/API-route risk. The tracked
`frontend-social-six` source folder and launcher were deleted after
owner-accepted external Supabase/Vercel/Railway/auth/API-route risk.

## Requirements

- Python with the backend dependencies installed
- Node.js with `npm`
- Frontend dependencies installed in each frontend you want to run
