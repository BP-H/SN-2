# Deployment And Media Preflight

Use this before an SN-2 alpha deployment, preview promotion, or SN-1 branch sync.
The goal is to prevent deployment/environment drift from looking like product
bugs, especially around uploaded images.

## Active Deployment Roots

- Active FE7 deploy root: `super-nova-2177/frontend-social-seven`
- Active backend source: `super-nova-2177/backend/app.py`
- Root compatibility backend entrypoint: `app.py`
- Protected core files must remain zero-diff:
  - `super-nova-2177/backend/supernova_2177_ui_weighted/supernovacore.py`
  - `super-nova-2177/frontend-vite-basic/supernovacore.py`

Do not point production at deleted legacy frontend folders. Historical cleanup
docs may mention them, but they are not active deploy roots.

## Environment Preflight

Record and verify:

- `NEXT_PUBLIC_API_URL` points at the intended backend API origin, with no
  accidental localhost value in production.
- `DATABASE_URL` points at the intended production or staging database.
- `UPLOADS_DIR` points at the intended upload volume/folder if local filesystem
  uploads are used.
- Any object-storage or durable-media env vars point at the intended bucket or
  service.
- Backend CORS mode matches the intended public/open-network posture.
- Rollback deploy target and env snapshot owner are recorded.

## Media Persistence Reality

Uploaded images and files are runtime state, not git state.

- Git does not carry old upload bytes.
- `/uploads/<file>` works only when that file exists in the active upload
  storage.
- The bounded DB-backed `data:image/...` fallback helps newly uploaded proposal
  images stored after the fallback shipped.
- Old posts whose stored record only contains a filename cannot be reconstructed
  from app code if the file bytes are gone.
- Restore old missing images from original files, backups, or durable storage if
  available.

## Image URL Probe

Before deploy:

1. Fetch `/proposals?filter=latest&limit=30` from the current backend.
2. Record a small sample of media URLs:
   - `/uploads/...`
   - `data:image/...`
   - external URLs, if any
3. Directly request sampled `/uploads/...` URLs and confirm HTTP 200 plus an
   image content type.

After deploy:

1. Fetch the same proposals endpoint from the target backend.
2. Confirm sampled `/uploads/...` URLs still return HTTP 200 when the file is
   expected to exist.
3. Confirm `data:image/...` entries remain data URLs and are not prefixed with
   the backend origin.
4. Upload one fresh image, refresh feed/detail, and confirm it still renders.

## Rollback

If media breaks after deploy:

1. Restore the previous FE7/backend deployment first.
2. Restore upload bytes to the expected `UPLOADS_DIR` or durable media store.
3. Restore database state only if the deploy changed data unexpectedly.
4. Re-run the image URL probe and manual image upload smoke.
