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
- `social-six`: `3001`
- `social-seven`: `3007`

`frontend-nova`, `frontend-professional`, `frontend-vite-3d`, and
`frontend-next` local launcher targets are retired/off-path. Use `social-seven`
for the active frontend. The `frontend-next` source folder remains in the repo
for deployment/auth/security assessment and is not an active local launcher.

## Requirements

- Python with the backend dependencies installed
- Node.js with `npm`
- Frontend dependencies installed in each frontend you want to run
