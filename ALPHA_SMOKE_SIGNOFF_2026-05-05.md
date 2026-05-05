# Alpha Smoke Signoff - 2026-05-05

This signoff records only observed evidence after PR #45 merged. No completed
manual browser smoke rows were supplied in the repository or prompt, so manual
rows are marked `NOT RUN`. Automated checks are recorded separately and are not
used to infer manual `PASS` results.

## Candidate

- Commit SHA: `dddc03f43288c91fa2c559f65da37bbad948682a`
- Branch or PR: `master` after PR #45
- Frontend URL: NOT PROVIDED
- Backend URL: `https://2177.tech` was checked by full `check_safe.py` public protocol smoke
- MCP URL, if checked: NOT PROVIDED
- Browser and version: NOT PROVIDED for manual smoke; mocked E2E used Playwright Chromium
- Device / viewport: NOT PROVIDED for manual smoke
- Operating system: Windows local workspace
- Smoke owner: Codex recorded automated evidence; manual smoke owner NOT PROVIDED
- Smoke date: 2026-05-05
- Previous known-good rollback target: NOT PROVIDED

## Automated Evidence

- FE7 lint/build: NOT RUN; no frontend source, config, or package files changed in this pass
- Mocked FE7 E2E (`npm run test:e2e` or `npm run test:e2e:mocked`): PASS, `PLAYWRIGHT_PORT=3017 npm run test:e2e` from `super-nova-2177/frontend-social-seven` reported 2 passed and 1 skipped
- Optional real-backend FE7 E2E (`PLAYWRIGHT_REAL_BACKEND=1 npm run test:e2e:real`): SKIPPED; no backend was available at `http://127.0.0.1:8000/health`
- Backend focused tests: PASS, `python -m py_compile super-nova-2177/backend/app.py`
- `python scripts/check_safe.py --local-only`: PASS through `super-nova-2177/.venv/Scripts/python.exe`
- Full `python scripts/check_safe.py`: PASS through `super-nova-2177/.venv/Scripts/python.exe`; live public protocol smoke reported 72 passed and 0 failed
- Protected core zero-diff: PASS through `check_safe.py --local-only`, full `check_safe.py`, and explicit protected-core diff checks

E2E remains advisory for this smoke pass. Do not treat mocked or real-backend
Playwright results as required branch-protection gates yet.

## Manual Smoke Rows

| Area | Status (`PASS` / `FAIL` / `BLOCKED` / `NOT RUN`) | Evidence / notes | Follow-up |
| --- | --- | --- | --- |
| Account signup/signin/signout | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Public signed-out feed/profile/proposal reads | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Status routes: `/health`, `/supernova-status`, `/status` | NOT RUN | Full safe check covered public protocol smoke, but this row was not manually clicked in browser. | Run from `ALPHA_SMOKE_NOW.md`. |
| Create/edit/delete post | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Fresh image upload renders after refresh | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Missing fresh upload fallback, if practical | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Legacy uploaded image path check | NOT RUN | No manual browser smoke evidence was provided. Already-missing bytes remain unrecoverable from app code alone. | Run from `ALPHA_SMOKE_NOW.md`; restore bytes from source files/backups/durable storage if available. |
| Comments/replies/edit/delete/votes | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Follows/unfollows | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Messages empty/conversation/send/reload | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| AI Genesis delegate creation/profile | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| AI review approve/cancel | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| AI comment approve/cancel | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| AI post approve/cancel | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| Mobile modal/feed sanity | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |
| MCP read-only posture | NOT RUN | No manual MCP smoke evidence was provided in this pass. | Run from `ALPHA_SMOKE_NOW.md`. |
| Rate-limit normal-use sanity | NOT RUN | No manual browser smoke evidence was provided. | Run from `ALPHA_SMOKE_NOW.md`. |

## Known Issues

| Issue | Impact | Status (`accepted` / `blocking` / `follow-up`) | Owner | Link |
| --- | --- | --- | --- | --- |
| Manual browser smoke evidence was not provided. | Alpha cannot be completed from this signoff alone. | blocking | Smoke owner | `ALPHA_SMOKE_NOW.md` |
| Real-backend FE7 E2E was skipped because local backend health was unavailable. | Public-read Playwright smoke against a real backend still needs a configured local/staging backend. | follow-up | Release owner | `super-nova-2177/frontend-social-seven/README.md` |
| Old uploaded images whose bytes are already missing cannot be reconstructed by app code alone. | Legacy image rows may remain broken unless bytes are restored from source files, backups, or durable storage. | follow-up | Release owner | `ALPHA_QA_CHECKLIST.md` |

Image persistence note: the bounded DB-backed `data:image/...` fallback protects
newly uploaded proposal images after the fallback shipped. Old images whose
upload bytes are already gone and whose database row only stores
`/uploads/<filename>` cannot be reconstructed by app code alone.

## Branch Protection Reminder

Branch protection has not been verified as enabled in GitHub settings during
this pass. `BRANCH_PROTECTION_ROLLOUT_STATUS.md` still records required checks
as not enabled.

For the first rollout, enable manually:

- `Require status checks to pass before merging`.
- `Require branches to be up to date before merging`.
- Required checks: `Backend local deterministic checks` and
  `FE7 local deterministic checks`.

Keep live/network smoke and advisory E2E unrequired until they are broader and
stable enough to avoid noisy blocking failures.

## Decision

- Smoke result (`PASS` / `FAIL` / `BLOCKED`): BLOCKED - automated guardrails passed, but no completed manual browser smoke rows were provided.
- Accepted exceptions: None recorded.
- Rollback target: NOT PROVIDED
- Follow-up PRs/issues: Run and record the manual browser smoke pass from `ALPHA_SMOKE_NOW.md`; configure a real local/staging backend before running `PLAYWRIGHT_REAL_BACKEND=1 npm run test:e2e:real`.
- Decision maker: NOT PROVIDED
- Decision timestamp: 2026-05-05
