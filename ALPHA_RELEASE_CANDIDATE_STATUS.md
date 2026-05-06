# Alpha Release Candidate Status

Date: 2026-05-06

This is a release-candidate blocker sweep for SN-2 after PR #67. It records
static inspection and automated evidence only. Manual browser smoke remains
`NOT RUN` unless a human-clicked result is supplied in a dated signoff.

## Candidate

- Candidate commit: `19a95a6`
- Branch context: `master` after PR #67
- RC sweep branch: `codex/alpha-rc-blocker-sweep`
- Active frontend: `super-nova-2177/frontend-social-seven`
- Active backend: `super-nova-2177/backend/app.py`
- Root compatibility backend entrypoint: `super-nova-2177/app.py`

## Blocker Sweep

Static inspection covered the active FE7 home/feed, composer, post card,
comments, messages, AI delegate modal, AI delegate picker, AI Genesis page,
API base helper, active backend entrypoint, and root compatibility entrypoint.

| Area | Status | Notes |
| --- | --- | --- |
| Signed-out home/feed | No confirmed blocker | Empty feed cue and public feed E2E coverage remain present. |
| Sign in / sign up entry points | No confirmed blocker | Account prompts are still used for signed-in actions; no public AI signup path was found in this sweep. |
| Create post/proposal UI | No confirmed blocker | Compact composer and expanded composer both expose post/media/AI entry points. |
| Comments UI | No confirmed blocker | Empty state, reply, AI comment, share, edit/delete ownership controls, and comment voting are present. |
| Vote UI | No confirmed blocker | Post and system vote controls remain visible; no rate-limit or semantics change was made. |
| Follow/message UI | No confirmed blocker | Follow/message paths and clean message empty states remain present. |
| Image upload display/refresh expectations | No confirmed blocker | FE7 preserves `data:` / `blob:` URLs and `/uploads/...` remains preferred when bytes exist. Fresh upload/manual refresh still requires browser smoke. |
| AI delegate create/generate/approve/cancel clarity | No confirmed blocker | The modal keeps create delegate, generate, approve, and cancel paths compact and approval-required. |
| Mobile obvious overflow/clutter | No confirmed blocker from static sweep | Modal, picker, comment menu, and message composer use bounded/internal scrolling patterns. Manual mobile smoke is still required. |

No runtime code was changed in this pass, and no tiny confirmed blocker required
a patch.

## Automated Checks

Record for this PR:

| Gate | Status |
| --- | --- |
| FE7 lint | PASS |
| FE7 build | PASS |
| Mocked FE7 E2E | PASS |
| Real-backend public E2E | PASS with local backend at `http://127.0.0.1:8000` |
| Backend compile | PASS |
| Alpha docs/static tests | PASS |
| Public data snapshot helper | PASS against local backend |
| `git diff --check` | PASS |
| Protected core zero-diff | PASS |
| `check_safe.py --local-only` | PASS |
| Full `check_safe.py` | PASS |

## Manual Smoke

Manual browser smoke status remains `NOT RUN`. Automated checks, static
inspection, backend probes, and E2E do not convert manual rows to `PASS`.

Use `ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md` or a dated copy of
`ALPHA_SMOKE_SIGNOFF_TEMPLATE.md` for human-clicked evidence. Use
`ALPHA_RELEASE_SMOKE_EXECUTION_PACK.md` for the short execution order.

## Data Preservation

The PR #67 data-preservation rule remains active. Follow
`DATA_PRESERVATION_PREFLIGHT.md` before any deploy promotion or later branch
sync:

- Do not run DB reset, seed, drop, truncate, migration reset, upload cleanup, or
  destructive local-state commands against production/staging data.
- Preserve `DATABASE_URL`, `UPLOADS_DIR` or durable media storage, and
  `NEXT_PUBLIC_API_URL`.
- Uploaded images/media are runtime state, not git state.
- Old missing upload bytes cannot be reconstructed without source files,
  backups, or durable storage.
- Use `scripts/public_data_snapshot.py <backend-url>` before and after deploy
  promotion.

## SN-1 Sync Status

SN-1 sync was not performed. Future SN-1 work should push SN-2 as a
non-default branch first, smoke a preview/staging deploy, compare public data
snapshots, and only then consider any merge or production promotion.

## Known Non-Blocking Caveats

- Human manual browser smoke is still incomplete.
- Branch protection has not been verified as enabled in GitHub settings. The
  candidate required check names are `Backend local deterministic checks` and
  `FE7 local deterministic checks`.
- Old images whose upload bytes are already gone remain unrecoverable from app
  code alone.
- Durable object storage or equivalent remains the long-term media direction.

## Recommendation

No confirmed release-candidate blocker was found in this automated/static pass.
Proceed to human manual alpha smoke next. Do not declare final release `GO`
until release-critical manual rows are completed or explicitly accepted by the
owner as exceptions.

## Rollback

This pass is docs/static-test only. Roll back by reverting the PR that adds this
status note and its static doc guard.
