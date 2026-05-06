# Data Preservation Preflight

Use this before an alpha release, deployment promotion, or later SN-2 to SN-1
branch sync. A git merge should not delete current posts, comments, votes,
messages, uploaded images, or media. Those live in runtime data stores, not in
git.

## Non-Negotiable Rules

- Never run database reset, seed, drop, truncate, migration-reset, or destructive
  cleanup commands against production.
- Never point a release deployment at a fresh empty database by accident.
- Preserve `DATABASE_URL` across release/deploy/sync work.
- Preserve `UPLOADS_DIR` or the configured durable media bucket across
  release/deploy/sync work.
- Preserve `NEXT_PUBLIC_API_URL` so FE7 continues talking to the intended
  backend API origin.
- Treat uploaded images and files as runtime state, not git state.
- Old missing uploaded bytes cannot be reconstructed from app code alone; they
  require source files, backups, or durable media storage.
- Take a database backup and an upload/media backup before deploy promotion or
  SN-1 branch-sync preview.
- Record a public `/proposals` sample before and after deploy so content and
  media URLs can be compared quickly.

## Required Backup Evidence

Before deploy or sync, record:

- Candidate git commit:
- Current production/staging backend URL:
- Current `DATABASE_URL` owner/location, without pasting secrets into git:
- Database backup identifier/path:
- Current upload/media storage owner/location:
- Upload/media backup identifier/path:
- Current `NEXT_PUBLIC_API_URL`:
- Rollback code target:
- Rollback data/media target:

Do not commit env files, database files, upload files, or secret values.

## Read-Only Snapshot

Use the public snapshot helper before and after deploy:

```powershell
python scripts/public_data_snapshot.py http://127.0.0.1:8000
```

The helper only performs unauthenticated GET requests:

- `/health`
- `/supernova-status`
- `/proposals?filter=latest&limit=30`

It outputs timestamp, backend URL, endpoint status, proposal count, proposal
IDs/titles, and sampled media URLs. It performs no writes, no auth, no database
access, no migrations, and no deletes.

## Destructive-Operation Audit Findings

Fresh repo search was run for obvious destructive/reset patterns:

- `drop_all`
- `create_all`
- `seed`
- `reset`
- `delete database`
- `rm uploads`
- `sqlite deletion`
- `migration reset`
- direct file/database deletion patterns

Findings:

- Active `super-nova-2177/backend/app.py` has additive SQLAlchemy
  `create_all` schema initialization in standalone fallback mode. This creates
  missing tables; it is not a drop/reset path.
- `super-nova-2177/backend/supernova_runtime.py` preserves an existing
  `DATABASE_URL` and only falls back to local SQLite when no env URL is set.
- Upload routes call `os.makedirs(uploads_dir, exist_ok=True)` and save new
  files; no active upload wipe path was found.
- Many backend tests call `Base.metadata.create_all(...)` against isolated test
  databases under temporary paths.
- `drop_all` matches were confined to legacy/protected-core tests or stubs, not
  active release startup.
- Nested audited legacy surfaces contain historical `create_all` and reset UI
  examples; they are retained/audited surfaces, not the active FE7/backend
  release path.

No confirmed active production destructive reset path was found in this pass.

## Release Compare Checklist

Before deploy:

1. Run `scripts/public_data_snapshot.py` against the current backend.
2. Save the JSON output outside git with the release evidence.
3. Sample any `/uploads/...` media URLs and confirm direct HTTP 200 responses
   when bytes are expected to exist.

After deploy:

1. Run the same snapshot helper against the target backend.
2. Confirm proposal sample count and IDs/titles are sane for the environment.
3. Confirm media URLs were preserved.
4. Upload one fresh image in manual smoke and refresh the feed/detail.

## Rollback Order

If content or images break after deploy:

1. Roll back FE7/backend code first.
2. Restore upload bytes or durable media storage to the expected location.
3. Restore the database only if data rows were changed unexpectedly.
4. Re-run the public snapshot helper and media URL probe.
