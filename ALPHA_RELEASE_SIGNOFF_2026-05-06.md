# Alpha Release Signoff - 2026-05-06

This checkpoint records the first alpha go/no-go posture after PR #70. It is a
release signoff note, not a runtime change.

## Decision Summary

- Owner smoke evidence: the owner manually checked the app and reported that
  the functions seem to be working.
- Evidence level: informal owner-reported smoke, not row-by-row detailed manual
  browser evidence.
- Automated gates: recent release-readiness PRs recorded passing deterministic
  backend, FE7, safe-check, protected-core, and advisory E2E gates. This PR
  reruns the docs/safe checks listed below.
- Known release blockers: no confirmed release blocker is known at this
  checkpoint.
- Recommendation: controlled alpha/preview `GO`.
- Final broader release recommendation: wait for detailed manual smoke rows or
  owner-accepted exceptions before declaring full release `GO`.

## Candidate

- Base commit before this signoff PR: `149e6cc97e90663e071885dad052dc3f0e6c20b5`
- Branch context: `master` after PR #70
- Signoff branch: `codex/alpha-release-signoff-checkpoint`
- Active frontend: `super-nova-2177/frontend-social-seven`
- Active backend: `super-nova-2177/backend/app.py`
- FE7 URL: `NOT PROVIDED`
- Backend URL: `NOT PROVIDED`
- Browser/device: owner checked the app informally; exact browser/device was
  `NOT PROVIDED`
- Operating system: `NOT PROVIDED`
- Smoke owner: owner note in PR #71 prompt
- Date: 2026-05-06
- Rollback target: latest merged SN-2 `master` before this docs-only signoff PR

## Manual Evidence Status

Do not infer detailed `PASS` rows from the owner summary. The note "functions
seem to be working" is useful release confidence, but it is not itemized
evidence for each release-critical flow.

| Flow | Status | Evidence / notes |
| --- | --- | --- |
| Overall active app functions | OWNER-REPORTED / NOT ITEMIZED | Owner manually checked the app and said the functions seem to be working. |
| Signed-out public feed renders | NOT RUN | No explicit row-level browser evidence was provided. |
| Signed-out profile and proposal detail render | NOT RUN | No explicit row-level browser evidence was provided. |
| Sign up as Human or Organization; AI is not offered as public species | NOT RUN | No explicit row-level browser evidence was provided. |
| Sign in, reload, and sign out | NOT RUN | No explicit row-level browser evidence was provided. |
| Create a post or proposal | NOT RUN | No explicit row-level browser evidence was provided. |
| Comment on a post | NOT RUN | No explicit row-level browser evidence was provided. |
| Vote/support and remove vote | NOT RUN | No explicit row-level browser evidence was provided. |
| Follow and unfollow another account | NOT RUN | No explicit row-level browser evidence was provided. |
| Open messages, send a message, reload thread | NOT RUN | No explicit row-level browser evidence was provided. |
| Upload image and confirm it renders after refresh | NOT RUN | No explicit row-level browser evidence was provided. |
| Existing `/uploads/...` image still renders when bytes exist | NOT RUN | No explicit row-level browser evidence was provided. |
| Old missing upload file recorded as unrecoverable without bytes/backups | NOT RUN | No explicit row-level browser evidence was provided. |
| Public data snapshot captured before deploy/preview | NOT RUN | No snapshot output was provided in this prompt. |
| Public data snapshot captured after deploy/preview and compared | NOT RUN | No snapshot output was provided in this prompt. |
| Create AI delegate through AI Genesis | NOT RUN | No explicit row-level browser evidence was provided. |
| Generate AI review draft | NOT RUN | No explicit row-level browser evidence was provided. |
| Approve AI review; one vote and rationale/comment publishes | NOT RUN | No explicit row-level browser evidence was provided. |
| Cancel AI review; nothing publishes | NOT RUN | No explicit row-level browser evidence was provided. |
| Generate AI comment draft, approve, and confirm expected comment/reply | NOT RUN | No explicit row-level browser evidence was provided. |
| Cancel AI comment; nothing publishes | NOT RUN | No explicit row-level browser evidence was provided. |
| Generate AI post draft, approve, and confirm one AI-authored post | NOT RUN | No explicit row-level browser evidence was provided. |
| Cancel AI post; nothing publishes | NOT RUN | No explicit row-level browser evidence was provided. |
| Mobile feed cards fit | NOT RUN | No explicit row-level browser evidence was provided. |
| Mobile composer remains usable | NOT RUN | No explicit row-level browser evidence was provided. |
| Mobile AI modal and delegate picker stay on-screen | NOT RUN | No explicit row-level browser evidence was provided. |
| `/health`, `/supernova-status`, and `/status` return stable JSON | NOT RUN | No explicit row-level browser evidence was provided. |
| Normal browsing does not hit rate limits | NOT RUN | No explicit row-level browser evidence was provided. |

## Branch Protection Status

Branch protection has not been verified as enabled in GitHub settings. Keep the
manual next action as:

- Enable `Require status checks to pass before merging`.
- Enable `Require branches to be up to date before merging`.
- Require exactly these checks first:
  - `Backend local deterministic checks`
  - `FE7 local deterministic checks`
- Keep live/network smoke and Playwright real-backend checks advisory until they
  are stable enough to be blocking gates.

## Deploy And Data-Preservation Next Actions

1. Merge this signoff PR if the docs/static checks pass.
2. Enable branch protection manually with the two deterministic checks above.
3. Deploy or preview FE7 with root `super-nova-2177/frontend-social-seven`.
4. Verify `NEXT_PUBLIC_API_URL` points to the intended backend.
5. Preserve and verify `DATABASE_URL`.
6. Preserve `UPLOADS_DIR` or the durable media storage bucket.
7. Run `python scripts/public_data_snapshot.py <backend-url>` before deploy or
   preview promotion.
8. Run a quick browser smoke using `ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md`.
9. Run `python scripts/public_data_snapshot.py <backend-url>` again after
   deploy or preview promotion and compare proposal count, IDs/titles, and
   sampled media URLs.
10. Fix only rows that are explicitly marked `FAIL` or `BLOCKED` with evidence.

## SN-1 Safety

SN-1 sync was not performed in this PR.

Future SN-1 sync remains later only and must start as a non-default-branch-first
preview. Preserve `DATABASE_URL`, uploaded media storage, and
`NEXT_PUBLIC_API_URL` before any deploy or branch sync. Git does not carry DB
rows, posts, comments, votes, messages, or uploaded image bytes.

Git does not carry DB rows or uploaded image bytes into SN-1; those are runtime
state and must be protected through database and media backups.

If images or data break after a deploy, roll back code first, then restore upload
bytes to the expected storage path, and restore DB state only if data was changed
unexpectedly.

## Release Recommendation

Controlled alpha/preview `GO` is reasonable based on the owner-reported smoke
and recent automated gates. Full broader release should wait until detailed
manual rows are completed or the owner explicitly accepts any unrun rows as
release exceptions.

## Rollback

This is a docs/static-test signoff PR. Roll back by reverting this PR. It does
not modify runtime code, backend route behavior, FE7 runtime behavior, uploads,
database files, env files, branch protection settings, or SN-1 branches.
