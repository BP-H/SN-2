# Preview Release Smoke - 2026-05-06

This checkpoint records the final post-merge alpha preview release gate
verification after PR #71. It is a verification note only; it does not change
runtime behavior, branch settings, deployment settings, database state, uploads,
or SN-1 branches.

## Candidate

- Verified commit: `b466d5063b9a8f14903937942b86ddf13a51834d`
- Branch context: latest SN-2 `master` after PR #71
- Verification branch: `codex/alpha-preview-release-gates`
- Active frontend: `super-nova-2177/frontend-social-seven`
- Active backend: `super-nova-2177/backend/app.py`
- Root compatibility backend entrypoint: `super-nova-2177/app.py`
- Preview/deploy URL: `NOT PROVIDED`

## Release Gate Results

| Gate | Status | Evidence |
| --- | --- | --- |
| Workflow check names exist | PASS | `.github/workflows/local-safe-pr-gates.yml` exposes `Backend local deterministic checks` and `FE7 local deterministic checks`. |
| Backend compile | PASS | `python -m py_compile super-nova-2177/backend/app.py`. |
| Alpha docs/static tests | PASS | `python -m unittest backend.tests.test_alpha_readiness_docs`. |
| Focused backend deterministic tests | PASS | Public federation safety, secret key hardening, DB engine consistency, DB fallback, read pagination baseline, and upload size limit tests passed. |
| FE7 lint | PASS | `npm run lint` from `super-nova-2177/frontend-social-seven`, using `npm.cmd` on Windows. |
| FE7 build | PASS | `npm run build` from `super-nova-2177/frontend-social-seven`. |
| Mocked FE7 E2E | PASS | `PLAYWRIGHT_PORT=3017 npm run test:e2e`; 3 passed, 1 real-backend spec skipped as expected. |
| Local backend health | PASS | Local backend started on `http://127.0.0.1:8000`; `/health` returned 200 JSON. |
| Public data snapshot helper | PASS | `scripts/public_data_snapshot.py http://127.0.0.1:8000` returned `/health`, `/supernova-status`, `/proposals?filter=latest&limit=30`, and 30 sampled proposals with media URLs. |
| Real-backend public FE7 E2E | PASS | `PLAYWRIGHT_REAL_BACKEND=1 NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 PLAYWRIGHT_PORT=3018 npm run test:e2e:real`; 1 passed. |
| `check_safe.py --local-only` | PASS | Local safe check passed. |
| Full `check_safe.py` | PASS | Full safe check passed after network approval for public protocol smoke. |
| Protected core zero-diff | PASS | No diff in both protected `supernovacore.py` paths. |
| `git diff --check` | PASS | No whitespace errors. |

## Branch Protection Readiness

The release-gate workflow is branch-protection-ready:

- `Backend local deterministic checks`
- `FE7 local deterministic checks`

Branch protection was not enabled by this PR. The public GitHub branch endpoint
reported `master` as `protected: false` on 2026-05-06, with required status
check enforcement `off`.

GitHub reported required status check enforcement `off`.

The owner asked to protect the branch, but this workspace has no `gh` CLI, no
GitHub token in the environment, and no connector tool that can mutate branch
protection/rulesets. The remaining required owner action is to enable branch
protection manually in GitHub settings:

No GitHub token was available. No connector tool can mutate branch protection
from this workspace.

- Enable `Require status checks to pass before merging`.
- Enable `Require branches to be up to date before merging`.
- Select only `Backend local deterministic checks` and `FE7 local deterministic
  checks` as required checks at first.

## Preview Deploy Smoke Readiness

No preview/deploy URL was provided in the prompt, repo docs, or local
environment. This does not block the code gate, but it means deploy smoke remains
the next owner action.

For preview deploy:

1. Deploy FE7 with root `super-nova-2177/frontend-social-seven`.
2. Keep backend entrypoint as `super-nova-2177/backend/app.py`, plus root
   compatibility `super-nova-2177/app.py` if the platform expects it.
3. Verify `NEXT_PUBLIC_API_URL` points to the intended backend.
4. Verify `DATABASE_URL` points to the intended data store.
5. Verify `UPLOADS_DIR` or durable media storage is preserved.
6. Run `python scripts/public_data_snapshot.py <backend-url>` before deploy or
   preview promotion.
7. Run quick browser smoke after deploy using
   `ALPHA_MANUAL_SMOKE_EVIDENCE_SHEET.md`.
8. Run `python scripts/public_data_snapshot.py <backend-url>` after deploy or
   preview promotion and compare proposal count, IDs/titles, and sampled media
   URLs.
9. Fix only explicit `FAIL` or `BLOCKED` rows.

## Manual Smoke Status

Manual browser smoke remains owner-reported but not fully itemized. The previous
owner note said the app functions seem to be working; this checkpoint does not
convert individual manual rows to `PASS`.

## SN-1 And Data Safety

SN-1 sync was not performed.

Do not run DB reset, seed, drop, truncate, migration reset, upload cleanup, env
changes, or SN-1 sync during release verification. Git does not carry DB rows or
uploaded image bytes. Preserve `DATABASE_URL`, `UPLOADS_DIR` or durable media
storage, and `NEXT_PUBLIC_API_URL` before any deploy or future SN-1
non-default-branch-first preview.

## Recommendation

Alpha preview release gates are green on latest SN-2 `master`. Proceed to manual
GitHub branch protection setup and preview deploy smoke. Controlled alpha/preview
remains `GO`; broader release should wait for detailed manual smoke rows or
owner-accepted exceptions.

Controlled alpha/preview remains `GO`.

## Rollback

This checkpoint is docs/static-test only. Revert this PR to remove the note. If a
future deploy breaks media, roll back code first, then restore upload bytes, and
restore DB only if data changed unexpectedly.
