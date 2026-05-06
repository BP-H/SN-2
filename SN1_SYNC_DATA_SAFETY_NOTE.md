# SN-1 Sync Data Safety Note

This is a future sync note only. Do not use this PR to sync SN-2 into SN-1.

## Safe Sync Shape

- Do not merge SN-2 into SN-1 `master` directly as the first step.
- Push SN-2 to SN-1 as a non-default branch first.
- Deploy only a preview or staging environment first.
- Verify FE7 points to the intended backend through `NEXT_PUBLIC_API_URL`.
- Verify backend deploy settings preserve `DATABASE_URL` and `UPLOADS_DIR` or
  durable media storage.
- Compare public data snapshots before and after preview deployment.
- Run manual browser smoke before any production merge or promotion.

## Runtime Data Reality

Git carries source code. Git does not carry:

- Database rows for posts, votes, comments, messages, follows, AI delegates, or
  profiles.
- Upload bytes in `/uploads/...`.
- Durable media bucket contents.
- Production/staging environment variables.

If a target environment points at a new empty database or missing media storage,
the app can look like posts or images disappeared even though the git merge did
not delete them.

## Snapshot Compare

Before and after SN-1 preview deploy:

```powershell
python scripts/public_data_snapshot.py <backend-url>
```

Compare:

- `/health` status.
- `/supernova-status` status.
- Proposal count in `/proposals?filter=latest&limit=30`.
- Proposal IDs/titles in the sample.
- `/uploads/...` and `data:image/...` media URLs.

## Rollback Order

If images or posts appear broken after preview/staging:

1. Roll back the code deployment first.
2. Restore upload bytes or media storage to the expected path/bucket.
3. Restore the database only if data rows were changed unexpectedly.
4. Re-run the snapshot helper and manual image smoke.
