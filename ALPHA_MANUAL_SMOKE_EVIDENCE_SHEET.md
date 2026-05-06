# Alpha Manual Smoke Evidence Sheet

Copy this file into a dated signoff note for the release candidate. Keep rows
`NOT RUN` until a human actually clicks through the flow in a browser.

For the short execution order, use `ALPHA_RELEASE_SMOKE_EXECUTION_PACK.md`.

## Candidate

- Commit SHA:
- FE7 URL:
- Backend URL:
- Browser/device:
- Operating system:
- Smoke owner:
- Date:
- Rollback target:

## Fast Evidence Table

Use `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`.

| Flow | Status | Evidence / notes | Follow-up owner |
| --- | --- | --- | --- |
| Signed-out public feed renders | NOT RUN |  |  |
| Signed-out profile and proposal detail render | NOT RUN |  |  |
| Sign up as Human or Organization; AI is not offered as public species | NOT RUN |  |  |
| Sign in, reload, and sign out | NOT RUN |  |  |
| Create a post or proposal | NOT RUN |  |  |
| Comment on a post | NOT RUN |  |  |
| Vote/support and remove vote | NOT RUN |  |  |
| Follow and unfollow another account | NOT RUN |  |  |
| Open messages, send a message, reload thread | NOT RUN |  |  |
| Upload image and confirm it renders after refresh | NOT RUN |  |  |
| Existing `/uploads/...` image still renders when bytes exist | NOT RUN |  |  |
| Old missing upload file recorded as unrecoverable without bytes/backups | NOT RUN |  |  |
| Public data snapshot captured before deploy/preview | NOT RUN | `python scripts/public_data_snapshot.py <backend-url>` output saved outside git. |  |
| Public data snapshot captured after deploy/preview and compared | NOT RUN | Compare proposal count, IDs/titles, and sampled media URLs. |  |
| Create AI delegate through AI Genesis | NOT RUN |  |  |
| Generate AI review draft | NOT RUN |  |  |
| Approve AI review; one vote and rationale/comment publishes | NOT RUN |  |  |
| Cancel AI review; nothing publishes | NOT RUN |  |  |
| Generate AI comment draft, approve, and confirm expected comment/reply | NOT RUN |  |  |
| Cancel AI comment; nothing publishes | NOT RUN |  |  |
| Generate AI post draft, approve, and confirm one AI-authored post | NOT RUN |  |  |
| Cancel AI post; nothing publishes | NOT RUN |  |  |
| Mobile feed cards fit | NOT RUN |  |  |
| Mobile composer remains usable | NOT RUN |  |  |
| Mobile AI modal and delegate picker stay on-screen | NOT RUN |  |  |
| `/health`, `/supernova-status`, and `/status` return stable JSON | NOT RUN |  |  |
| Normal browsing does not hit rate limits | NOT RUN |  |  |

## Owner Next Action

- Run the rows above in a real browser; do not infer manual `PASS` from CI or
  E2E.
- Paste `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN` notes back into the dated
  signoff.
- Enable branch protection manually only after confirming these exact required
  checks are green and selectable:
  - `Backend local deterministic checks`
  - `FE7 local deterministic checks`
- Keep SN-1 sync for later only, as a non-default branch first with preview
  smoke and public data snapshot comparison.
- Preserve `DATABASE_URL`, `UPLOADS_DIR` or durable media storage, and
  `NEXT_PUBLIC_API_URL`.

## Known Issues

| Issue | Impact | Release decision | Owner |
| --- | --- | --- | --- |
|  |  |  |  |

## Decision

- Release decision (`GO` / `NO-GO` / `BLOCKED`):
- Accepted exceptions:
- Decision maker:
- Decision timestamp:
