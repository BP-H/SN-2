# Alpha Release Smoke Execution Pack

Use this pack for the first human alpha release smoke. It is intentionally
short: run the release-critical flows, paste real evidence, fix only confirmed
blockers, and keep everything else `NOT RUN`.

No human-clicked smoke evidence was present when this pack was added, so no
manual row was marked `PASS`.

## Owner Next Action

1. Copy `ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md` into a dated signoff note.
2. Fill commit SHA, FE7 URL, backend URL, browser/device, owner, date, and
   rollback target.
3. Run a public data snapshot before the deploy or preview promotion:
   `python scripts/public_data_snapshot.py <backend-url>`.
4. Click each release-critical row in a real browser and mark only observed
   `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`.
5. Upload one fresh image, refresh feed/detail, and check old `/uploads/...`
   images where practical.
6. Run a public data snapshot after the deploy or preview promotion and compare
   proposal count, IDs/titles, and sampled media URLs.
7. Paste the filled evidence back into the PR or dated signoff file.
8. Enable branch protection manually only after confirming these exact checks
   are green and selectable:
   - `Backend local deterministic checks`
   - `FE7 local deterministic checks`
9. Keep SN-1 sync for later only, as a non-default-branch-first preview.

## Local Helper Order

These commands are convenience helpers only. They do not replace human browser
clicks.

```powershell
# Terminal 1: backend
cd super-nova-2177
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000

# Terminal 2: FE7
cd super-nova-2177\frontend-social-seven
npm run dev

# Terminal 3: read-only public snapshot and advisory E2E
python scripts/public_data_snapshot.py http://127.0.0.1:8000
cd super-nova-2177\frontend-social-seven
$env:PLAYWRIGHT_PORT='3017'; npm run test:e2e
$env:PLAYWRIGHT_REAL_BACKEND='1'; $env:NEXT_PUBLIC_API_URL='http://127.0.0.1:8000'; $env:PLAYWRIGHT_PORT='3018'; npm run test:e2e:real
```

## Release-Critical Human Flows

Mark rows in `ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md`; do not mark this section
directly.

- Signed-out public feed, profile, proposal detail, and status JSON reads.
- Sign up as Human or Organization; confirm public signup does not offer AI as
  a standalone account species.
- Sign in, reload, sign out.
- Create a post/proposal, comment, vote/support, follow/unfollow, and send a
  message.
- Upload a fresh image and confirm it renders after refresh.
- Check old `/uploads/...` images where practical; already-missing bytes are
  unrecoverable without source files, backups, or durable storage.
- Create an AI delegate through AI Genesis.
- Generate AI review, AI comment, and AI post drafts.
- Approve and cancel AI drafts; confirm nothing publishes before approval.
- Check mobile feed, composer, AI modal, delegate picker, and account modal.

## Data Safety

- Do not run DB reset, seed, drop, truncate, migration reset, or upload cleanup.
- Preserve `DATABASE_URL`, `UPLOADS_DIR` or durable media storage, and
  `NEXT_PUBLIC_API_URL`.
- Git does not carry posts, comments, votes, messages, upload bytes, or DB rows.
- Roll back code first if media breaks, then restore upload bytes, then restore
  DB only if data changed unexpectedly.

## Stop Conditions

Stop and file/fix a focused blocker PR if any release-critical row is `FAIL` and
has evidence. Keep unrelated polish, redesign, backend route work, cleanup, and
SN-1 sync out of the smoke pass.
