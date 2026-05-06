# Alpha Smoke Checkpoint - 2026-05-06 After FE7 Polish

This checkpoint records automated alpha-smoke readiness evidence after PR #64
merged. It does not mark any manual browser smoke row as passed. Human-clicked
manual smoke evidence was not provided in this pass, so manual rows remain
`NOT RUN`.

## Candidate

- Commit SHA: `45b0a3240214c225583709a663a1892a2111f763`
- Branch or PR: `master` after PR #64
- Frontend URL tested by mocked E2E: `http://127.0.0.1:3017`
- Frontend URL tested by real-backend E2E: `http://127.0.0.1:3018`
- Backend URL tested: `http://127.0.0.1:8000`
- Public protocol smoke URL: `https://2177.tech`
- Browser/device: Playwright Chromium desktop for automated E2E only
- Operating system: Windows local workspace
- Smoke owner: Codex recorded automated evidence only
- Date: 2026-05-06

## Docs Reviewed

- `ALPHA_SMOKE_NOW.md`
- `ALPHA_QA_CHECKLIST.md`
- `ALPHA_SMOKE_SIGNOFF_2026-05-05.md`
- `LEGACY_FRONTEND_CLEANUP_CLOSEOUT.md`

PR #64's FE7 copy and empty-state polish does not require checklist wording
changes. Existing smoke rows already cover signed-out feed reads, clean message
empty states, comments, AI Genesis, AI delegate approval flows, and advisory
FE7 E2E.

## Automated Evidence

- FE7 lint: PASS, `npm run lint` from `super-nova-2177/frontend-social-seven`
- FE7 build: PASS, `npm run build` from `super-nova-2177/frontend-social-seven`
- Mocked FE7 E2E: PASS, `PLAYWRIGHT_PORT=3017 npm run test:e2e` reported 2
  passed and 1 optional real-backend spec skipped
- Backend compile: PASS, `.venv` Python compiled `super-nova-2177/backend/app.py`
- Local backend probes: PASS, `/health`, `/supernova-status`, and
  `/proposals?filter=latest&limit=30` returned HTTP 200 from
  `http://127.0.0.1:8000`
- Real-backend public E2E: PASS,
  `PLAYWRIGHT_REAL_BACKEND=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 PLAYWRIGHT_PORT=3018 npm run test:e2e:real`
  reported 1 passed
- `git diff --check`: PASS
- Protected core zero-diff: PASS
- `check_safe.py --local-only`: PASS through repo `.venv` Python
- Full `check_safe.py`: PASS through repo `.venv` Python with network
  permission for the live public protocol smoke; public protocol smoke reported
  72 passed and 0 failed

The first full `check_safe.py` attempt without network permission hit Windows
socket error `WinError 10013` on the live public protocol smoke. The rerun with
network permission passed.

## Manual Smoke Rows

Automated checks are not used to infer manual pass results.

| Area | Status | Evidence / notes |
| --- | --- | --- |
| Account signup/signin/signout | NOT RUN | No human-clicked browser evidence provided. |
| Public signed-out feed/profile/proposal reads | NOT RUN | Automated public-read E2E passed, but no manual browser evidence provided. |
| Status routes in browser | NOT RUN | Local probes passed, but no manual browser evidence provided. |
| Create/edit/delete post | NOT RUN | No human-clicked browser evidence provided. |
| Fresh image upload and refresh | NOT RUN | No human-clicked browser evidence provided. |
| Legacy uploaded image path check | NOT RUN | No human-clicked browser evidence provided. Already-missing bytes remain unrecoverable from app code alone. |
| Comments/replies/edit/delete/votes | NOT RUN | No human-clicked browser evidence provided. |
| Follows/unfollows | NOT RUN | No human-clicked browser evidence provided. |
| Messages empty/conversation/send/reload | NOT RUN | No human-clicked browser evidence provided. |
| AI Genesis delegate creation/profile | NOT RUN | No human-clicked browser evidence provided. |
| AI review/comment/post approve/cancel | NOT RUN | No human-clicked browser evidence provided. |
| Mobile modal/feed sanity | NOT RUN | No human-clicked browser evidence provided. |
| MCP read-only posture | NOT RUN | No manual MCP evidence provided. |
| Rate-limit normal-use sanity | NOT RUN | No human-clicked browser evidence provided. |

## Blockers

- Confirmed automated blockers found: none.
- Confirmed runtime blockers fixed in this pass: none.
- Manual alpha smoke remains incomplete until a human browser pass is recorded.

## Intentionally Not Changed

- No runtime code changes.
- No backend route/helper semantics.
- No protected core changes.
- No schema, upload, database, env, Docker Compose, rate-limit, branch
  protection, or deleted-frontend changes.
- No AI safety or publishing semantics changes.

## Rollback

Rollback is a single revert of this checkpoint document. It contains no runtime
behavior changes and no data migration.
